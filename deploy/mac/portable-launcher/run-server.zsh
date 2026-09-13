#!/bin/zsh
# 由 macOS launchd 调用；参数均由 Soda Prompt Hub 启动器提供。

emulate -L zsh
setopt no_unset

repository="$1"
uv_bin="$2"
python_bin="$3"
host="$4"
port="$5"
pid_file="$6"
server_log="$7"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1
export ORT_DISABLE_TELEMETRY="${ORT_DISABLE_TELEMETRY:-1}"

print -r -- "$$" > "$pid_file"
exec >> "$server_log" 2>&1

if [[ -x "$python_bin" ]]; then
  exec "$python_bin" -m prompt_hub serve --host "$host" --port "$port"
fi
exec "$uv_bin" run --project "$repository" --no-sync prompt-hub serve --host "$host" --port "$port"
