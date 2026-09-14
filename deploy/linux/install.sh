#!/usr/bin/env bash
#
# Soda Prompt Hub — Linux 安装脚本
#
# 做四件事：准备依赖（uv sync）→ 建立用户数据目录 → 安装 systemd 用户服务 → 健康检查。
# 不需要 sudo，不会修改系统级配置，不会删除任何用户数据。
#
# 用法:
#   ./deploy/linux/install.sh [选项]
#
# 选项:
#   --host <地址>          监听地址（默认 127.0.0.1；非回环地址会给出警告）
#   --port <端口>          监听端口（默认 8765）
#   --library-root <路径>  资料库根目录（默认 $XDG_DATA_HOME/soda-prompt-hub/library）
#   --models-root <路径>   模型根目录（默认 <资料库父目录>/models）
#   --no-service           只准备依赖与目录，不安装 systemd 服务
#   --enable-linger        额外执行 loginctl enable-linger（默认不做，见 README）
#   --force                已存在安装记录时，允许覆盖（不会删除数据）
#   -h, --help             显示本帮助

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
    sed -n '3,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

HOST="${SPH_DEFAULT_HOST}"
PORT="${SPH_DEFAULT_PORT}"
LIBRARY_ROOT=""
MODELS_ROOT=""
INSTALL_SERVICE=1
ENABLE_LINGER=0
FORCE=0

while (($# > 0)); do
    case "$1" in
        --host)
            HOST="${2:?--host 需要一个参数}"
            shift 2
            ;;
        --port)
            PORT="${2:?--port 需要一个参数}"
            shift 2
            ;;
        --library-root)
            LIBRARY_ROOT="${2:?--library-root 需要一个参数}"
            shift 2
            ;;
        --models-root)
            MODELS_ROOT="${2:?--models-root 需要一个参数}"
            shift 2
            ;;
        --no-service)
            INSTALL_SERVICE=0
            shift
            ;;
        --enable-linger)
            ENABLE_LINGER=1
            shift
            ;;
        --force)
            FORCE=1
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            sph_err "未知参数：$1"
            usage >&2
            exit 2
            ;;
    esac
done

[[ "${PORT}" =~ ^[0-9]+$ ]] || sph_die "--port 必须是数字：${PORT}"
((PORT >= 1 && PORT <= 65535)) || sph_die "--port 超出范围：${PORT}"

sph_require_linux

REPO_ROOT="$(sph_repo_root)"
[[ -f "${REPO_ROOT}/pyproject.toml" && -d "${REPO_ROOT}/src/prompt_hub" ]] ||
    sph_die "没有在 ${REPO_ROOT} 找到项目文件；请从仓库内的 deploy/linux/install.sh 运行"

printf 'Soda Prompt Hub — Linux 安装\n'
printf '仓库: %s\n' "${REPO_ROOT}"
printf '监听: %s:%s\n\n' "${HOST}" "${PORT}"

if [[ "${HOST}" != "127.0.0.1" && "${HOST}" != "localhost" && "${HOST}" != "::1" ]]; then
    sph_warn "监听地址是 ${HOST}，不只是本机。默认应保持 127.0.0.1（主任务书 §25）。"
fi

# ---------------------------------------------------------------- 1. 既有安装
if sph_load_install_env 2>/dev/null; then
    sph_info "检测到既有安装：${SPH_INSTALLED_AT:-未知时间}"
    if ((FORCE == 0)); then
        # 未加 --force 时沿用已有配置，避免重装把数据目录指到别处
        [[ -n "${LIBRARY_ROOT}" ]] || LIBRARY_ROOT="${SPH_LIBRARY_ROOT}"
        [[ -n "${MODELS_ROOT}" ]] || MODELS_ROOT="${SPH_MODELS_ROOT}"
        [[ "${HOST}" == "${SPH_DEFAULT_HOST}" ]] && HOST="${SPH_HOST:-${SPH_DEFAULT_HOST}}"
        [[ "${PORT}" == "${SPH_DEFAULT_PORT}" ]] && PORT="${SPH_PORT:-${SPH_DEFAULT_PORT}}"
        sph_info "沿用既有数据目录（如需更改请加 --force 或显式传参）"
    fi
fi

DATA_HOME="$(sph_data_home)"
[[ -n "${LIBRARY_ROOT}" ]] || LIBRARY_ROOT="${DATA_HOME}/library"
[[ -n "${MODELS_ROOT}" ]] || MODELS_ROOT="$(dirname -- "${LIBRARY_ROOT}")/models"
LIBRARY_ROOT="$(sph_abs_path "${LIBRARY_ROOT}")"
MODELS_ROOT="$(sph_abs_path "${MODELS_ROOT}")"

# ---------------------------------------------------------------- 2. 环境检查
printf -- '--- 环境检查 ---\n'

sph_require_cmd uv "安装方式见 https://docs.astral.sh/uv/ ；或 sudo apt install pipx && pipx install uv"
sph_ok "uv: $(uv --version)"

if command -v git >/dev/null 2>&1; then
    sph_ok "git: $(git --version)"
else
    sph_warn "未找到 git；update.sh 将无法使用（安装本身不受影响）"
fi

if command -v curl >/dev/null 2>&1; then
    sph_ok "curl: $(curl --version | head -n1)"
else
    sph_warn "未找到 curl；安装后的健康检查会跳过"
fi

if command -v python3 >/dev/null 2>&1; then
    PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo unknown)"
    sph_ok "python3: ${PY_VERSION}（项目要求 >=3.12；uv 会自行准备合适解释器）"
else
    sph_warn "未找到系统 python3；uv 会自行下载受管 Python（需要网络）"
fi

if [[ "${INSTALL_SERVICE}" -eq 1 ]] && ! sph_have_systemd_user; then
    sph_warn "当前会话没有 systemd 用户会话；将跳过服务安装（可用 start.sh 直接前台/后台运行）"
    INSTALL_SERVICE=0
fi

# ---------------------------------------------------------------- 3. 目录
printf -- '\n--- 用户数据目录 ---\n'
if [[ "${LIBRARY_ROOT}" == "${DATA_HOME}/library" ]]; then
    mkdir -p "${DATA_HOME}"
    chmod 700 "${DATA_HOME}"
fi
mkdir -p "${LIBRARY_ROOT}/database" "${MODELS_ROOT}"
sph_ok "资料库: ${LIBRARY_ROOT}"
sph_ok "模型:   ${MODELS_ROOT}"

# ---------------------------------------------------------------- 4. 依赖
printf -- '\n--- 安装依赖（uv sync --locked）---\n'
(
    cd "${REPO_ROOT}"
    uv sync --locked
)
[[ -x "${REPO_ROOT}/.venv/bin/prompt-hub" ]] ||
    sph_die "uv sync 完成，但未找到 ${REPO_ROOT}/.venv/bin/prompt-hub"
sph_ok "虚拟环境就绪：${REPO_ROOT}/.venv"

# ---------------------------------------------------------------- 5. 便利命令
printf -- '\n--- 便利命令 ---\n'
LAUNCHER="$(sph_launcher_path)"
mkdir -p "$(dirname -- "${LAUNCHER}")"
install -m 0755 "${SCRIPT_DIR}/soda-prompt-hub.sh" "${LAUNCHER}"
sph_ok "已安装：${LAUNCHER}"
case ":${PATH}:" in
    *":$(dirname -- "${LAUNCHER}"):"*) ;;
    *) sph_warn "$(dirname -- "${LAUNCHER}") 不在 PATH 中；请把 export PATH=\"\$HOME/.local/bin:\$PATH\" 加入 ~/.bashrc" ;;
esac

# ---------------------------------------------------------------- 6. systemd 服务
if [[ "${INSTALL_SERVICE}" -eq 1 ]]; then
    printf -- '\n--- systemd 用户服务 ---\n'
    UNIT_PATH="$(sph_unit_path)"
    mkdir -p "$(dirname -- "${UNIT_PATH}")"
    TEMPLATE="${SCRIPT_DIR}/${SPH_SERVICE_NAME}.service"
    [[ -f "${TEMPLATE}" ]] || sph_die "缺少服务模板：${TEMPLATE}"
    UNIT_CONTENT="$(cat "${TEMPLATE}")"
    UNIT_CONTENT="${UNIT_CONTENT//__SPH_REPO__/${REPO_ROOT}}"
    UNIT_CONTENT="${UNIT_CONTENT//__SPH_LIBRARY_ROOT__/${LIBRARY_ROOT}}"
    UNIT_CONTENT="${UNIT_CONTENT//__SPH_MODELS_ROOT__/${MODELS_ROOT}}"
    UNIT_CONTENT="${UNIT_CONTENT//__SPH_HOST__/${HOST}}"
    UNIT_CONTENT="${UNIT_CONTENT//__SPH_PORT__/${PORT}}"
    printf '%s\n' "${UNIT_CONTENT}" >"${UNIT_PATH}"
    chmod 0644 "${UNIT_PATH}"
    sph_ok "已写入 ${UNIT_PATH}"

    sph_systemd_daemon_reload
    sph_systemd_enable
    if sph_service_active; then
        sph_systemd_restart
        sph_ok "服务已重启（配置更新）"
    else
        sph_systemd_start
        sph_ok "服务已启动"
    fi

    if ((ENABLE_LINGER == 1)); then
        if command -v loginctl >/dev/null 2>&1; then
            loginctl enable-linger "${USER}" && sph_ok "已开启 linger（用户注销后服务继续运行）"
        else
            sph_warn "未找到 loginctl，跳过 --enable-linger"
        fi
    else
        sph_info "未开启 linger：注销当前用户会话后服务会停止（需要常驻请加 --enable-linger）"
    fi
else
    printf -- '\n--- 跳过 systemd 服务 ---\n'
    sph_info "使用 ./deploy/linux/start.sh 启动，或直接运行："
    sph_info "  PROMPT_HUB_LIBRARY_ROOT=${LIBRARY_ROOT} ${REPO_ROOT}/.venv/bin/prompt-hub serve --host ${HOST} --port ${PORT}"
fi

# ---------------------------------------------------------------- 7. 安装记录
ENV_FILE="$(sph_install_env_path)"
mkdir -p "$(dirname -- "${ENV_FILE}")"
{
    printf '# Soda Prompt Hub 安装记录（由 deploy/linux/install.sh 生成，可被 source）\n'
    printf 'SPH_INSTALLED_AT=%q\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    printf 'SPH_REPO=%q\n' "${REPO_ROOT}"
    printf 'SPH_LIBRARY_ROOT=%q\n' "${LIBRARY_ROOT}"
    printf 'SPH_MODELS_ROOT=%q\n' "${MODELS_ROOT}"
    printf 'SPH_HOST=%q\n' "${HOST}"
    printf 'SPH_PORT=%q\n' "${PORT}"
    printf 'SPH_SERVICE=%q\n' "$([[ "${INSTALL_SERVICE}" -eq 1 ]] && echo yes || echo no)"
} >"${ENV_FILE}"
chmod 0644 "${ENV_FILE}"

# ---------------------------------------------------------------- 8. 健康检查
printf -- '\n--- 健康检查 ---\n'
if [[ "${INSTALL_SERVICE}" -eq 1 ]]; then
    if sph_wait_health 30; then
        sph_ok "服务已就绪：$(sph_health_url)"
        sph_info "打开浏览器访问 http://${HOST}:${PORT}"
    else
        sph_err "服务在 30 秒内未通过健康检查"
        sph_info "排查：systemctl --user status ${SPH_SERVICE_NAME} ; journalctl --user -u ${SPH_SERVICE_NAME} -n 50"
        exit 1
    fi
else
    sph_info "未安装服务，跳过健康检查"
fi

printf -- '\n===== 安装完成 =====\n'
printf '仓库:   %s\n' "${REPO_ROOT}"
printf '资料库: %s\n' "${LIBRARY_ROOT}"
printf '模型:   %s\n' "${MODELS_ROOT}"
printf '地址:   http://%s:%s\n' "${HOST}" "${PORT}"
printf '记录:   %s\n' "${ENV_FILE}"
if [[ "${INSTALL_SERVICE}" -eq 1 ]]; then
    printf '\n常用命令:\n'
    printf '  systemctl --user status %s\n' "${SPH_SERVICE_NAME}"
    printf '  journalctl --user -u %s -f\n' "${SPH_SERVICE_NAME}"
    printf '  %s status\n' "$(sph_launcher_path)"
fi
printf '\n程序更新不会改动资料库、模型与数据库（见 update.sh）。\n'
