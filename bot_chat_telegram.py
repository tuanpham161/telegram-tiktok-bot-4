import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from pydub import AudioSegment
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip
from tiktok_uploader.upload import upload_video
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

ROOT_FOLDER = r"/tmp/lambaotiktok"
COOKIES_LIST = [{"name": "sessionid", "value": "bbf8f1e1c87dd8c1ecfb90d529b10497"}]

TELEGRAM_TOKEN = "7549467659:AAGZBZvI5ToML4zQ2BtagLwGzSYsxNI9nxo"  # <-- thay bằng token bot của bạn
YOUR_CHAT_ID = 7549467659  # <-- thay bằng chat_id của bạn

# --- Các hàm xử lý ---
def get_article_content_images_and_audio(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip("/").split("/")
    slug_full = path_parts[-1].replace(".htm", "")
    article_id_match = re.search(r"(\d{17,})$", slug_full)
    if not article_id_match:
        raise Exception("❌ Không tìm thấy ID bài viết.")
    article_id = article_id_match.group(1)
    date_match = re.search(r"(\d{4})(\d{2})(\d{2})", article_id)
    year, month, day = date_match.groups()
    folder = os.path.join(ROOT_FOLDER, slug_full)
    os.makedirs(folder, exist_ok=True)

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    article = soup.find('article')
    for figcaption in article.find_all('figcaption'):
        figcaption.decompose()
    title = soup.find("h1", class_="title-page detail").get_text(strip=True)
    sapo_tag = soup.find("h2", class_="singular-sapo")
    sapo = sapo_tag.get_text(strip=True) if sapo_tag else ""
    paragraphs = article.find_all('p')
    article_text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    full_text = re.sub(r"\(Dân trí\)\s*-\s*", "", title + "\n\n" + sapo + "\n" + article_text)
    with open(os.path.join(folder, "noidung.txt"), "w", encoding="utf-8") as f:
        f.write(full_text)

    count = 0
    for img in article.find_all('img'):
        if img.find_parent('a', class_='author-avatar__picture'):
            continue
        src = img.get("data-original") or img.get("data-src") or img.get("src")
        if src:
            img_url = requests.compat.urljoin(url, src)
            img_data = requests.get(img_url, headers=headers).content
            with open(os.path.join(folder, f"img_{count + 1}.jpg"), "wb") as f_img:
                f_img.write(img_data)
            count += 1

    audio_url = f"https://acdn.dantri.com.vn/{year}/{int(month)}/{int(day)}/{article_id}/full_1.mp3"
    audio_response = requests.get(audio_url, headers=headers)
    if audio_response.status_code == 200:
        with open(os.path.join(folder, "audio.mp3"), "wb") as f_audio:
            f_audio.write(audio_response.content)
    return folder

def get_audio_duration(audio_path):
    audio = AudioSegment.from_file(audio_path)
    return audio.duration_seconds

def create_video_from_images_audio(folder_path):
    images = sorted([f for f in os.listdir(folder_path) if f.endswith(('.jpg', '.jpeg', '.png'))])
    audio_files = [f for f in os.listdir(folder_path) if f.endswith('.mp3')]
    audio_path = os.path.join(folder_path, audio_files[0])
    duration_per_image = get_audio_duration(audio_path) / len(images)
    clips = [ImageClip(os.path.join(folder_path, img)).set_duration(duration_per_image) for img in images]
    video = concatenate_videoclips(clips, method="compose").set_audio(AudioFileClip(audio_path))
    output_path = os.path.join(folder_path, "output_video.mp4")
    video.write_videofile(output_path, fps=24)
    return output_path

def upload_to_tiktok(video_path, folder_path):
    description = ""
    noidung_path = os.path.join(folder_path, "noidung.txt")
    if os.path.exists(noidung_path):
        with open(noidung_path, "r", encoding="utf-8") as f:
            description = f.read().strip() + "\n#tinhanh247 #fyp #viral"
    upload_video(video_path, description=description, cookies_list=COOKIES_LIST, headless=True)


# --- Xử lý tin nhắn Telegram ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Gửi link bài báo Dân Trí để bắt đầu!")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "dantri.com.vn" not in url:
        await update.message.reply_text("❌ Vui lòng gửi link hợp lệ từ Dân Trí.")
        return

    try:
        await update.message.reply_text("📥 Đang tải nội dung...")
        folder = get_article_content_images_and_audio(url)
        await update.message.reply_text("📥 Đã tải nội dung xong.")

        await update.message.reply_text("🖼️ Đang tạo video...")
        video_path = create_video_from_images_audio(folder)
        await update.message.reply_text(f"🖼️ Đã tạo video xong tại: {video_path}")

        await update.message.reply_text("📤 Đang đăng lên TikTok...")
        upload_to_tiktok(video_path, folder)
        await update.message.reply_text("✅ Đã đăng video thành công!")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")

# --- Khởi động bot ---
def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    print("🤖 Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    run_bot()
