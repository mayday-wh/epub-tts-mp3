# EPUB to MP3 TTS v1.1

把当前文件夹里的 EPUB 转成章节 MP3，也可以合并成整本 MP3。默认使用 Microsoft Edge 的中文自然语音：

```powershell
uv run epub_tts.py convert ".\哲学家的最后一课_朱锐.epub"
```

输出会放在同名文件夹里：

- `chapters\`：每章一个 MP3
- `chapters.m3u`：章节播放列表
- `哲学家的最后一课.mp3`：整本合并后的 MP3
- `book_text_preview.txt`：抽取出来的文本预览，方便检查章节是否正常

转换前可以先检查 EPUB 拆章效果：

```powershell
uv run epub_tts.py inspect ".\哲学家的最后一课_朱锐.epub"
```

## 换音色

先列出中文音色：

```powershell
uv run epub_tts.py voices --locale zh-CN
```

转换时指定你喜欢的音色：

```powershell
uv run epub_tts.py convert ".\哲学家的最后一课_朱锐.epub" --voice zh-CN-YunxiNeural
```

常用参数：

```powershell
uv run epub_tts.py convert ".\哲学家的最后一课_朱锐.epub" --voice zh-CN-XiaoxiaoNeural --rate -5% --pitch +0Hz
```

如果只想生成章节文件，不合并整本：

```powershell
uv run epub_tts.py convert ".\哲学家的最后一课_朱锐.epub" --no-merge
```

## 图形界面

双击：

```powershell
run_ui.bat
```

或在命令行运行：

```powershell
uv run --managed-python epub_tts_ui.py
```

界面支持：

- 拖入或选择 EPUB 文件
- 自动读取章节列表
- 勾选需要转换的章节
- 选择中文 TTS 音色、语速、音调、音量
- 生成章节 MP3，并可合并为整本 MP3
