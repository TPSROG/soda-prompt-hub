from prompt_hub.web_resources import read_web_asset

OPTIONAL_MODELS_STYLES = "<style>" + read_web_asset("optional_models.css") + "</style>"
OPTIONAL_MODELS_SCRIPT = "<script>" + read_web_asset("optional_models.js") + "</script>"
OPTIONAL_MODELS_HTML = """
<dialog id="optionalModelsDialog" class="model-installer" aria-labelledby="optionalModelsTitle" aria-describedby="optionalModelsIntro">
  <header class="model-installer-head"><div><p class="section-label">LOCAL TOOLS / 按需添加</p><h2 id="optionalModelsTitle">本地模型，可选安装。</h2><p id="optionalModelsIntro">只安装你用得上的能力。跳过不影响项目管理、外部 API 或 ComfyUI 出图。</p></div><button type="button" id="optionalModelsClose" class="model-close" aria-label="关闭模型安装界面">关闭 ×</button></header>
  <div class="model-host"><strong id="optionalModelsHost">正在确认安装设备…</strong><span>安装位置由 WebUI 服务所在设备决定，不是浏览器所在设备；不会自动安装到远程 Worker。</span><code id="optionalModelsRoot"></code></div>
  <div class="model-installer-guide"><span><b>01</b> 选择用途</span><span><b>02</b> 下载 · 可取消续传</span><span><b>03</b> 校验 · 本机自检</span></div>
  <p id="optionalModelsNotice" class="model-notice" role="status" aria-live="polite">正在读取模型状态…</p>
  <div id="optionalModelsList" class="model-install-list"></div>
  <footer class="model-installer-foot"><div><strong>不上传图片，也不消耗 API 额度。</strong><p>模型文件从 Hugging Face 下载，网络需能访问该站点。下载后会进行 CPU 推理自检，短暂占用内存；不自动生成标签、不替换人工说明、不切换已有自定义 CLIP。</p><p>已有文件不会被静默覆盖。也可按卡片中的目录手动放入相同版本的文件，再校验。关闭此窗口，下载仍会继续。</p></div><button type="button" id="optionalModelsServices">语言／看图模型？前往模型接入 →</button></footer>
</dialog>
"""
