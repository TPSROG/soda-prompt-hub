#!/bin/zsh
# Soda Prompt Hub —— 无 Terminal 的 macOS 便携启动器核心

emulate -L zsh
setopt no_unset pipe_fail

HOST="${PROMPT_HUB_HOST:-127.0.0.1}"
PORT="${PROMPT_HUB_PORT:-8765}"
URL="http://${HOST}:${PORT}/"
STARTUP_TIMEOUT="${PROMPT_HUB_LAUNCHER_TIMEOUT:-120}"
STATE_ROOT="${PROMPT_HUB_LAUNCHER_STATE_ROOT:-$HOME/Library/Application Support/Soda Prompt Hub}"
LOG_ROOT="${PROMPT_HUB_LAUNCHER_LOG_ROOT:-$HOME/Library/Logs/Soda Prompt Hub}"
PID_FILE="$STATE_ROOT/prompt-hub.pid"
LOCK_DIR="$STATE_ROOT/launcher.lock"
LAUNCHER_LOG="$LOG_ROOT/launcher.log"
SERVER_LOG="$LOG_ROOT/server.log"
LAUNCH_AGENT_PLIST="$STATE_ROOT/server-launch-agent.plist"
SCRIPT_PATH="${0:A}"
APP_ROOT="${SCRIPT_PATH:h:h:h}"
APP_PARENT="${APP_ROOT:h}"
RUNNER_PATH="$APP_ROOT/Contents/Resources/run-server.zsh"
LAUNCHD_LABEL="com.soda.prompt-hub.server"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$STATE_ROOT" "$LOG_ROOT" || exit 1

timestamp() {
  /bin/date '+%Y-%m-%d %H:%M:%S'
}

log() {
  print -r -- "[$(timestamp)] $*" >> "$LAUNCHER_LOG"
}

show_error() {
  local title="$1"
  local message="$2"
  log "ERROR: $title — $message"
  if [[ -n "${PROMPT_HUB_LAUNCHER_DIALOG_LOG:-}" ]]; then
    print -r -- "$title: $message" >> "$PROMPT_HUB_LAUNCHER_DIALOG_LOG"
    return
  fi
  /usr/bin/osascript - "$title" "$message" <<'APPLESCRIPT' > /dev/null 2>&1 || true
on run argv
  display alert (item 1 of argv) message (item 2 of argv) as critical buttons {"好"} default button "好"
end run
APPLESCRIPT
}

open_page() {
  log "打开页面：$URL"
  if [[ "${PROMPT_HUB_LAUNCHER_SKIP_OPEN:-0}" != "1" ]]; then
    /usr/bin/open "$URL"
  fi
}

is_prompt_hub() {
  /usr/bin/curl -fsS --max-time 2 "${URL}api/health" 2> /dev/null \
    | /usr/bin/grep -Eq '"service"[[:space:]]*:[[:space:]]*"soda-prompt-hub"'
}

port_in_use() {
  /usr/sbin/lsof -nP -iTCP:"$PORT" -sTCP:LISTEN > /dev/null 2>&1
}

release_lock() {
  /bin/rm -f "$LOCK_DIR/pid" 2> /dev/null || true
  /bin/rmdir "$LOCK_DIR" 2> /dev/null || true
}

acquire_lock() {
  if /bin/mkdir "$LOCK_DIR" 2> /dev/null; then
    print -r -- "$$" > "$LOCK_DIR/pid"
    trap release_lock EXIT INT TERM HUP
    return 0
  fi

  local owner_pid=""
  if [[ -r "$LOCK_DIR/pid" ]]; then
    IFS= read -r owner_pid < "$LOCK_DIR/pid"
  fi
  if [[ "$owner_pid" == <-> ]] && /bin/kill -0 "$owner_pid" 2> /dev/null; then
    return 1
  fi
  if [[ -z "$owner_pid" ]]; then
    local lock_modified="0"
    local now="0"
    lock_modified="$(/usr/bin/stat -f '%m' "$LOCK_DIR" 2> /dev/null || print -r -- 0)"
    now="$(/bin/date '+%s')"
    if [[ "$lock_modified" == <-> ]] && (( now - lock_modified < STARTUP_TIMEOUT )); then
      return 1
    fi
  fi

  /bin/rm -f "$LOCK_DIR/pid" 2> /dev/null || true
  /bin/rmdir "$LOCK_DIR" 2> /dev/null || return 1
  /bin/mkdir "$LOCK_DIR" 2> /dev/null || return 1
  print -r -- "$$" > "$LOCK_DIR/pid"
  trap release_lock EXIT INT TERM HUP
}

valid_repository() {
  local candidate="$1"
  [[ -f "$candidate/pyproject.toml" && -d "$candidate/src/prompt_hub" ]]
}

find_repository() {
  local hint_file="$APP_ROOT/Contents/Resources/repository-path"
  local hint=""
  local candidate=""
  local -a candidates

  if [[ -n "${PROMPT_HUB_REPO:-}" ]]; then
    candidates+=("$PROMPT_HUB_REPO")
  fi
  if [[ -r "$hint_file" ]]; then
    IFS= read -r hint < "$hint_file"
    [[ -n "$hint" ]] && candidates+=("$hint")
  fi
  candidates+=(
    "$APP_PARENT"
    "${APP_PARENT:h}"
    "$HOME/Applications/Soda Prompt Hub"
  )

  for candidate in "${candidates[@]}"; do
    [[ -n "$candidate" ]] || continue
    candidate="${candidate:A}"
    if valid_repository "$candidate"; then
      print -r -- "$candidate"
      return 0
    fi
  done
  return 1
}

find_uv() {
  local candidate=""
  if [[ -n "${PROMPT_HUB_UV_BIN:-}" ]]; then
    [[ -x "$PROMPT_HUB_UV_BIN" ]] || return 1
    print -r -- "$PROMPT_HUB_UV_BIN"
    return 0
  fi
  for candidate in \
    "$HOME/.local/bin/uv" \
    "$HOME/.cargo/bin/uv" \
    "/opt/homebrew/bin/uv" \
    "/usr/local/bin/uv"; do
    if [[ -x "$candidate" ]]; then
      print -r -- "$candidate"
      return 0
    fi
  done
  return 1
}

rotate_server_log() {
  local size="0"
  [[ -f "$SERVER_LOG" ]] || return 0
  size="$(/usr/bin/stat -f '%z' "$SERVER_LOG" 2> /dev/null || print -r -- 0)"
  if [[ "$size" == <-> && "$size" -gt 10485760 ]]; then
    /bin/mv -f "$SERVER_LOG" "$SERVER_LOG.previous"
  fi
}

write_launch_agent_plist() {
  local repository="$1"
  local uv_bin="$2"
  local python_bin="$3"

  /usr/bin/plutil -create xml1 "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert Label -string "$LAUNCHD_LABEL" "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProgramArguments -array "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProgramArguments.0 -string "$RUNNER_PATH" "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProgramArguments.1 -string "$repository" "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProgramArguments.2 -string "$uv_bin" "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProgramArguments.3 -string "$python_bin" "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProgramArguments.4 -string "$HOST" "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProgramArguments.5 -string "$PORT" "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProgramArguments.6 -string "$PID_FILE" "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProgramArguments.7 -string "$SERVER_LOG" "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert ProcessType -string Interactive "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert Nice -integer 0 "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert LowPriorityIO -bool false "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert KeepAlive -bool false "$LAUNCH_AGENT_PLIST" &&
    /usr/bin/plutil -insert RunAtLoad -bool false "$LAUNCH_AGENT_PLIST"
}

start_service() {
  local repository="$1"
  local python_bin="$repository/.venv/bin/python"
  local uv_bin=""
  local service_pid=""
  local launchctl_bin="${PROMPT_HUB_LAUNCHCTL_BIN:-/bin/launchctl}"
  local -a command

  if uv_bin="$(find_uv)"; then
    command=("$uv_bin" run --no-sync prompt-hub serve --host "$HOST" --port "$PORT")
  elif [[ -x "$python_bin" ]]; then
    command=("$python_bin" -m prompt_hub serve --host "$HOST" --port "$PORT")
  else
    return 2
  fi

  rotate_server_log
  log "启动程序：$repository"
  /bin/rm -f "$PID_FILE" 2> /dev/null || true

  if [[ "${PROMPT_HUB_LAUNCHER_NO_LAUNCHD:-0}" == "1" ]]; then
    local previous_directory="$PWD"
    cd "$repository" || return 1
    export PYTHONUNBUFFERED=1
    /usr/bin/nohup "${command[@]}" >> "$SERVER_LOG" 2>&1 < /dev/null &
    service_pid="$!"
    print -r -- "$service_pid" > "$PID_FILE"
    cd "$previous_directory" || return 1
  else
    [[ -x "$launchctl_bin" && -x "$RUNNER_PATH" ]] || return 1
    write_launch_agent_plist "$repository" "$uv_bin" "$python_bin" || return 1
    local launchd_domain="gui/$(/usr/bin/id -u)"
    "$launchctl_bin" bootout "$launchd_domain/$LAUNCHD_LABEL" > /dev/null 2>&1 || true
    "$launchctl_bin" bootstrap "$launchd_domain" "$LAUNCH_AGENT_PLIST" || return 1
    "$launchctl_bin" kickstart -k "$launchd_domain/$LAUNCHD_LABEL" || return 1
    for _ in {1..30}; do
      [[ -r "$PID_FILE" ]] && break
      /bin/sleep 0.1
    done
    [[ -r "$PID_FILE" ]] || return 1
    IFS= read -r service_pid < "$PID_FILE"
  fi

  log "后台进程：$service_pid"

  local attempt=0
  while (( attempt < STARTUP_TIMEOUT )); do
    if is_prompt_hub; then
      log "服务已就绪"
      open_page
      return 0
    fi
    if [[ "$service_pid" == <-> ]] && ! /bin/kill -0 "$service_pid" 2> /dev/null; then
      break
    fi
    /bin/sleep 1
    (( attempt += 1 ))
  done
  return 1
}

log "收到启动请求"

if is_prompt_hub; then
  log "服务已经运行"
  open_page
  exit 0
fi

if port_in_use; then
  show_error "Soda Prompt Hub 无法启动" \
    "端口 $PORT 已被其他程序占用。Prompt Hub 没有结束该程序。"
  exit 1
fi

if ! acquire_lock; then
  log "另一个启动请求正在处理中"
  for _ in {1..15}; do
    if is_prompt_hub; then
      open_page
      exit 0
    fi
    /bin/sleep 1
  done
  show_error "Soda Prompt Hub 正在启动" "请稍等片刻后再次双击。"
  exit 0
fi

if is_prompt_hub; then
  open_page
  exit 0
fi

repository="$(find_repository)" || {
  show_error "找不到 Soda Prompt Hub" \
    "请先运行首次安装器，或把启动器放回完整源码包附近。"
  exit 1
}

start_service "$repository"
launch_status=$?
if [[ "$launch_status" -eq 0 ]]; then
  exit 0
fi

if [[ "$launch_status" -eq 2 ]]; then
  show_error "缺少运行组件" "没有找到项目运行环境或 uv。请先运行首次安装器。"
else
  show_error "Soda Prompt Hub 启动失败" \
    "请查看日志：$SERVER_LOG"
fi
exit 1
