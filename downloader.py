import subprocess
import json
import re
import os
import zipfile
import urllib.request
import platform
from utils import log_event

class Downloader:
    def __init__(self, archive_path="archive.txt", cookies_file=None):
        self.archive_path = archive_path
        self.cookies_file = cookies_file
        self.ffmpeg_path = None
        self.setup_ffmpeg()

    def setup_ffmpeg(self):
        """FFmpeg'i uygulamaya özel olarak kurar"""
        # FFmpeg klasörü oluştur
        ffmpeg_dir = os.path.join(os.path.dirname(__file__), "ffmpeg")
        if not os.path.exists(ffmpeg_dir):
            os.makedirs(ffmpeg_dir)
        
        # FFmpeg executable'ının yolu
        if platform.system() == "Windows":
            self.ffmpeg_path = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        else:
            self.ffmpeg_path = os.path.join(ffmpeg_dir, "ffmpeg")
        
        # FFmpeg yüklü değilse indir
        if not os.path.exists(self.ffmpeg_path):
            self.download_ffmpeg(ffmpeg_dir)
        
        log_event(f"FFmpeg yolu: {self.ffmpeg_path}")

    def download_ffmpeg(self, ffmpeg_dir):
        """FFmpeg'i indirir ve kurar"""
        try:
            log_event("FFmpeg indiriliyor...")
            
            if platform.system() == "Windows":
                # Windows için FFmpeg indir
                ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
                zip_path = os.path.join(ffmpeg_dir, "ffmpeg.zip")
                
                # ZIP dosyasını indir
                urllib.request.urlretrieve(ffmpeg_url, zip_path)
                
                # ZIP'i aç
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(ffmpeg_dir)
                
                # ZIP dosyasını sil
                os.remove(zip_path)
                
                # Executable'ı doğru konuma taşı
                extracted_dir = None
                for item in os.listdir(ffmpeg_dir):
                    item_path = os.path.join(ffmpeg_dir, item)
                    if os.path.isdir(item_path) and item.startswith("ffmpeg"):
                        extracted_dir = item_path
                        break
                
                if extracted_dir:
                    # bin klasöründen ffmpeg.exe'yi kopyala
                    bin_dir = os.path.join(extracted_dir, "bin")
                    if os.path.exists(bin_dir):
                        import shutil
                        shutil.copy2(os.path.join(bin_dir, "ffmpeg.exe"), self.ffmpeg_path)
                        # Geçici klasörü sil
                        shutil.rmtree(extracted_dir)
                
                log_event("FFmpeg Windows için başarıyla indirildi ve kuruldu")
            else:
                # Linux/Mac için FFmpeg kurulumu
                log_event("Linux/Mac için FFmpeg kurulumu: Lütfen 'sudo apt install ffmpeg' veya 'brew install ffmpeg' komutunu çalıştırın")
                self.ffmpeg_path = "ffmpeg"  # Sistem PATH'inden kullan
                
        except Exception as e:
            log_event(f"FFmpeg indirme hatası: {str(e)}")
            self.ffmpeg_path = "ffmpeg"  # Sistem PATH'inden kullanmaya çalış

    def check_ffmpeg(self):
        try:
            log_event(f"FFmpeg path check: {self.ffmpeg_path}")
            if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
                log_event("FFmpeg dosyası bulundu, çalıştırılıyor...")
                result = subprocess.run([self.ffmpeg_path, "-version"], capture_output=True, text=True)
                log_event(f"FFmpeg run result: {result.returncode}, stdout: {result.stdout}, stderr: {result.stderr}")
                if result.returncode == 0:
                    log_event("FFmpeg bulundu (uygulama içi): Birleştirme işlemi mümkün")
                    return True
            else:
                log_event("FFmpeg dosyası bulunamadı, sistem PATH deneniyor...")
                result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
                log_event(f"FFmpeg PATH run result: {result.returncode}, stdout: {result.stdout}, stderr: {result.stderr}")
                if result.returncode == 0:
                    log_event("FFmpeg bulundu (sistem): Birleştirme işlemi mümkün")
                    self.ffmpeg_path = "ffmpeg"
                    return True
                else:
                    log_event("FFmpeg bulunamadı: Birleştirme işlemi yapılamayacak")
                    return False
        except Exception as e:
            log_event(f"FFmpeg kontrolünde hata: {e}")
            return False

    def get_video_info(self, url):
        log_event(f"get_video_info çağrıldı: url={url}")
        # Playlist mi kontrol et
        if "playlist" in url or "list=" in url:
            command = ["yt-dlp", "--dump-single-json"]
            if self.cookies_file and os.path.exists(self.cookies_file):
                command.extend(["--cookies", self.cookies_file])
            if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
                command.extend(["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)])
            command.append(url)
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
            if result.returncode != 0:
                log_event(f"get_video_info hata: {result.stderr}")
                return None, result.stderr
            try:
                data = json.loads(result.stdout)
                if data.get("_type") == "playlist" and "entries" in data:
                    videos = [entry for entry in data["entries"] if entry]
                    log_event(f"get_video_info tamamlandı: {len(videos)} video bulundu (playlist).")
                    return videos, None
            except Exception as e:
                log_event(f"get_video_info JSON parse error: {e}")
                return None, str(e)
        # Playlist değilse eski yöntem
        command = ["yt-dlp", "--flat-playlist", "--dump-json"]
        if self.cookies_file and os.path.exists(self.cookies_file):
            command.extend(["--cookies", self.cookies_file])
        if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
            command.extend(["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)])
        command.append(url)
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            log_event(f"get_video_info hata: {result.stderr}")
            return None, result.stderr
        videos = []
        playlist_video_ids = []
        is_playlist = False
        for line in result.stdout.strip().split('\n'):
            try:
                data = json.loads(line)
                # Playlist ise _type=playlist, video ise _type=video
                if data.get('_type') == 'playlist' or data.get('ie_key') == 'YoutubePlaylist':
                    is_playlist = True
                    # Playlist içindeki video id'lerini topla
                    if 'entries' in data:
                        for entry in data['entries']:
                            if isinstance(entry, dict) and 'id' in entry:
                                playlist_video_ids.append(entry['id'])
                            elif isinstance(entry, str):
                                playlist_video_ids.append(entry)
                elif data.get('_type') == 'url' and 'id' in data:
                    is_playlist = True
                    playlist_video_ids.append(data['id'])
                elif 'id' in data and data.get('_type') is None:
                    # Bazı yt-dlp çıktılarında sadece id string'i dönebilir
                    playlist_video_ids.append(data['id'])
                else:
                    videos.append(data)
            except json.JSONDecodeError:
                continue
        # Eğer playlist ise, her video için detaylı bilgi çek
        if is_playlist and playlist_video_ids:
            detailed_videos = []
            for vid in playlist_video_ids:
                vid_url = f"https://www.youtube.com/watch?v={vid}"
                cmd = ["yt-dlp", "--dump-json"]
                if self.cookies_file and os.path.exists(self.cookies_file):
                    cmd.extend(["--cookies", self.cookies_file])
                cmd.append(vid_url)
                res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
                if res.returncode == 0:
                    try:
                        detailed_videos.append(json.loads(res.stdout.strip()))
                    except Exception:
                        continue
            log_event(f"get_video_info tamamlandı: {len(detailed_videos)} video bulundu (playlist).")
            return detailed_videos, None
        log_event(f"get_video_info tamamlandı: {len(videos)} video bulundu.")
        return videos, None

    def _run_yt_dlp_command(self, command, thread_id="unknown"):
        log_event(f"yt-dlp komutu başlatıldı: {' '.join(command)}")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                 text=True, bufsize=1, universal_newlines=True, 
                                 encoding='utf-8', errors='replace')
        current_title = None
        current_ext = None
        video_title = None
        
        for line in iter(process.stdout.readline, ''):
            # Her satırı log olarak gönder
            yield {"type": "log", "message": line.strip()}
            
            # Video title'ı yakala - [info] satırından
            if "[info]" in line and ":" in line:
                # Video title'ı çıkar - daha spesifik kontroller
                if "Downloading 1 format(s):" in line:
                    # Format bilgisini atla
                    continue
                elif "Writing video subtitles to" in line:
                    # Altyazı yazma mesajını atla
                    continue
                elif "Available formats for" in line:
                    # Format listesi mesajını atla  
                    continue
                else:
                    # Gerçek video title'ını yakala
                    info_match = re.search(r'\[info\]\s+(.+?):', line)
                    if info_match and not any(keyword in line.lower() for keyword in ['format', 'downloading', 'available', 'playlist', 'writing', 'subtitle']):
                        potential_title = info_match.group(1).strip()
                        if len(potential_title) > 10 and not potential_title.startswith('http') and not potential_title.startswith('['):
                            video_title = potential_title
                            log_event(f"Video title yakalandı: {video_title}")
            
            # Video title'ını daha güvenilir bir şekilde yakala
            if line.startswith('[youtube]') and ': Downloading webpage' in line:
                # YouTube video ID'sinden sonra gelen title'ı yakala
                youtube_match = re.search(r'\[youtube\]\s+(.+?):\s+Downloading webpage', line)
                if youtube_match:
                    video_id = youtube_match.group(1).strip()
                    log_event(f"YouTube video ID yakalandı: {video_id}")
            
            # Daha güvenilir title yakalama
            if '[download] Destination:' in line and not video_title:
                dest_line = line.strip()
                # Dosya yolundan title'ı çıkar
                dest_match = re.search(r'Destination:\s+(.+)', dest_line)
                if dest_match:
                    file_path = dest_match.group(1).strip()
                    filename = os.path.basename(file_path)
                    # Dosya adından title'ı çıkar (uzantıyı kaldır)
                    title_from_file = os.path.splitext(filename)[0]
                    # Format kodlarını temizle (örn: .f137, .f140)
                    title_cleaned = re.sub(r'\.[f]\d+$', '', title_from_file)
                    if len(title_cleaned) > 5 and not video_title:
                        video_title = title_cleaned
                        log_event(f"Video title dosya adından yakalandı: {video_title}")
            
            # Birleştirme işlemi bilgilerini yakala
            if "[Merger]" in line or "[ffmpeg]" in line:
                log_event(f"Birleştirme işlemi: {line.strip()}")
            
            # [download] Destination: ... satırını yakala
            if "[download] Destination:" in line:
                dest = line.strip().split(":", 1)[-1].strip()
                # Dosya adı ve uzantısını ayıkla
                filename = os.path.basename(dest)
                current_title, current_ext = os.path.splitext(filename)
                if current_ext.startswith('.'):
                    current_ext = current_ext[1:]
                log_event(f"Destination yakalandı: title={current_title}, ext={current_ext}")
            
            # Parse progress - daha basit ve esnek regex pattern
            # [download]   3.9% of  355.08MiB at    3.74MiB/s ETA 01:31
            if "[download]" in line and "%" in line and " of " in line and " at " in line:
                # Daha esnek regex ile parse et
                progress_match = re.search(r'(\d+\.\d+)%.*?of\s+(\S+).*?at\s+(\S+)(?:.*?ETA\s+(\S+))?', line)
                if progress_match:
                    # En iyi title'ı belirle
                    display_title = video_title or current_title or "Unknown"
                    display_ext = current_ext or "Unknown"
                    
                    # Önce log eventini gönder
                    progress_log = f"İndirme ilerlemesi: %{progress_match.group(1)} of {progress_match.group(2)} at {progress_match.group(3)} ETA {progress_match.group(4) if progress_match.group(4) else 'N/A'} | {display_title}.{display_ext}"
                    yield {"type": "log", "message": progress_log}
                    
                    # Sonra progress eventini gönder
                    progress = {
                        "type": "progress",
                        "percent": float(progress_match.group(1)),
                        "total_size": progress_match.group(2),
                        "speed": progress_match.group(3),
                        "eta": progress_match.group(4) if progress_match.group(4) else "N/A",
                        "title": display_title,
                        "ext": display_ext,
                        "thread_id": thread_id
                    }
                    yield progress
            
            # Format seçimi bilgisini yakala
            format_match = re.search(r'\[info\]\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', line)
            if format_match:
                format_id = format_match.group(1)
                extension = format_match.group(2)
                resolution = format_match.group(3)
                filesize = format_match.group(4)
                log_event(f"Format seçildi: ID={format_id}, Ext={extension}, Res={resolution}, Size={filesize}")
        
        process.stdout.close()
        process.wait()
        
        stderr_output = process.stderr.read()
        if process.returncode != 0:
            log_event(f"yt-dlp hata: {stderr_output.strip()}")
            yield {"type": "error", "message": stderr_output.strip(), "thread_id": thread_id, "title": video_title or current_title or "Unknown"}
        else:
            log_event("yt-dlp tamamlandı: Download finished.")
            yield {"type": "complete", "message": "Download finished.", "thread_id": thread_id, "title": video_title or current_title or "Unknown"}

    def download_videos(self, urls, download_options, output_path):
        log_event(f"download_videos çağrıldı: urls={urls}, options={download_options}, output_path={output_path}")
        thread_id = download_options.get("thread_id", "unknown")
        base_command = ["yt-dlp"]
        
        # Add cookies if available
        if self.cookies_file and os.path.exists(self.cookies_file):
            base_command.extend(["--cookies", self.cookies_file])
        
        # Add ffmpeg location if available
        if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
            base_command.extend(["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)])
        
        # Add output path
        if output_path:
            base_command.extend(["-o", f"{output_path}/%(playlist)s/%(title)s.%(ext)s"])
        else:
            base_command.extend(["-o", "%(playlist)s/%(title)s.%(ext)s"]) # Default to current directory

        # Add quality options with better format selection
        quality = download_options.get("quality", "bestvideo+bestaudio/best")
        merge_video_audio = download_options.get("merge_video_audio", True)
        
        # Video/audio birleştirme ayarları
        if merge_video_audio:
            # FFmpeg kontrolü
            if not self.check_ffmpeg():
                log_event("Uyarı: FFmpeg bulunamadı, birleştirme işlemi devre dışı bırakılıyor")
                merge_video_audio = False
            else:
                # FFmpeg ile otomatik birleştirme - kaliteyi koruyacak parametreler
                base_command.extend(["--merge-output-format", "mkv"])
                # Post-processor olarak FFmpeg kullan - uygulama içi FFmpeg'i kullan
                if self.ffmpeg_path and self.ffmpeg_path != "ffmpeg":
                    base_command.extend(["--postprocessor-args", f"ffmpeg:-c:v copy -c:a aac -strict experimental"])
                    # FFmpeg yolunu belirt
                    base_command.extend(["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)])
                else:
                    base_command.extend(["--postprocessor-args", "ffmpeg:-c:v copy -c:a aac -strict experimental"])
                # Audio kalitesini artır
                base_command.extend(["--audio-quality", "0"])
                # Audio formatını belirt
                base_command.extend(["--audio-format", "m4a"])
                # Birleştirme işlemi hakkında detaylı bilgi
                log_event("Birleştirme ayarları: mkv format, FFmpeg ile video ve ses birleştirme aktif")
        
        if not merge_video_audio:
            log_event("Birleştirme devre dışı: Video ve ses dosyaları ayrı ayrı indirilecek")
        
        # Daha spesifik format seçimi - kaliteyi garanti etmek için
        if quality == "best":
            base_command.extend(["-f", "best"])
            log_event("Format seçimi: best")
        elif quality == "bestvideo+bestaudio/best":
            # En iyi video + en iyi ses, yüksek kalite öncelikli
            base_command.extend(["-f", "bestvideo[height>=720]+bestaudio/best[height>=720]/bestvideo+bestaudio/best"])
            log_event("Format seçimi: bestvideo[height>=720]+bestaudio/best[height>=720]/bestvideo+bestaudio/best")
        elif quality == "4K":
            base_command.extend(["-f", "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[height<=2160]/best"])
            log_event("Format seçimi: 4K - bestvideo[height<=2160]+bestaudio")
        elif quality == "1440p":
            base_command.extend(["-f", "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[height<=1440]/best"])
            log_event("Format seçimi: 1440p - bestvideo[height<=1440]+bestaudio")
        elif quality == "1080p":
            base_command.extend(["-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"])
            log_event("Format seçimi: 1080p - bestvideo[height<=1080]+bestaudio")
        elif quality == "720p":
            base_command.extend(["-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best"])
            log_event("Format seçimi: 720p - bestvideo[height<=720]+bestaudio")
        elif quality == "480p":
            base_command.extend(["-f", "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best"])
            log_event("Format seçimi: 480p - bestvideo[height<=480]+bestaudio")
        elif quality == "360p":
            base_command.extend(["-f", "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]/best"])
            log_event("Format seçimi: 360p - bestvideo[height<=360]+bestaudio")
        elif quality == "worst":
            base_command.extend(["-f", "worst"])
            log_event("Format seçimi: worst")
        else:
            # Varsayılan olarak en iyi kalite
            base_command.extend(["-f", "bestvideo[height>=720]+bestaudio/best[height>=720]/bestvideo+bestaudio/best"])
            log_event("Format seçimi: default - bestvideo[height>=720]+bestaudio")

        # Add subtitle options
        if download_options.get("download_subtitles"):
            subtitle_lang = download_options.get("subtitle_language", "tr")
            if subtitle_lang == "all":
                base_command.extend(["--write-subs", "--all-subs"]) # Download all available subtitles
            else:
                base_command.extend(["--write-subs", "--sub-langs", subtitle_lang]) # Download specific language
        
        # Add auto-translated subtitles
        if download_options.get("auto_subtitles"):
            auto_lang = download_options.get("auto_translate_language", "tr")
            base_command.extend(["--write-auto-subs", "--sub-langs", auto_lang]) # Download auto-generated subtitles in specific language

        # Embed subtitles into video
        if download_options.get("embed_subtitles"):
            base_command.extend(["--embed-subs"]) # Embed subtitles into video file
            log_event("Altyazılar video dosyasına gömülecek")

        # Add concurrent downloads
        concurrent_fragments = int(download_options.get("concurrent_fragments", 5))
        base_command.extend(["--concurrent-fragments", str(concurrent_fragments)])

        # Add download archive
        base_command.extend(["--download-archive", self.archive_path])

        for url in urls:
            log_event(f"İndirme başlatılıyor: {url}")
            command = base_command + [url]
            log_event(f"Tam yt-dlp komutu: {' '.join(command)}")
            yield {"type": "status", "message": f"Starting download for: {url}"}
            for progress_update in self._run_yt_dlp_command(command, thread_id):
                yield progress_update
            log_event(f"İndirme tamamlandı: {url}")

    def set_cookies_file(self, cookies_file):
        """Set the cookies file path for authentication"""
        self.cookies_file = cookies_file
