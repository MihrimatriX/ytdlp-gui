import os
import json
import sqlite3
import shutil
import tempfile
import subprocess
import platform
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
from utils import log_event

try:
    import win32crypt
    WINDOWS_CRYPT_AVAILABLE = True
except ImportError:
    WINDOWS_CRYPT_AVAILABLE = False
    print("Warning: win32crypt not available. Cookie decryption may not work properly.")

class CookieExtractor:
    def __init__(self):
        self.system = platform.system()
        self.output_file = "youtube_cookies.txt"
        
    def get_chrome_cookies_path(self):
        """Chrome cookies dosyasının yolunu bulur"""
        if self.system == "Windows":
            chrome_path = os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Network\\Cookies")
            if os.path.exists(chrome_path):
                return chrome_path
        elif self.system == "Darwin":  # macOS
            chrome_path = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Cookies")
            if os.path.exists(chrome_path):
                return chrome_path
        elif self.system == "Linux":
            chrome_path = os.path.expanduser("~/.config/google-chrome/Default/Cookies")
            if os.path.exists(chrome_path):
                return chrome_path
        return None

    def get_edge_cookies_path(self):
        """Edge cookies dosyasının yolunu bulur"""
        if self.system == "Windows":
            edge_base_path = os.path.expanduser("~\\AppData\\Local\\Microsoft\\Edge\\User Data")
            if os.path.exists(edge_base_path):
                # Önce Default klasörünü dene
                default_path = os.path.join(edge_base_path, "Default", "Network", "Cookies")
                if os.path.exists(default_path):
                    return default_path
                
                # Sonra Profile klasörlerini dene
                for item in os.listdir(edge_base_path):
                    if item.startswith("Profile "):
                        profile_path = os.path.join(edge_base_path, item, "Network", "Cookies")
                        if os.path.exists(profile_path):
                            return profile_path
        elif self.system == "Darwin":  # macOS
            edge_path = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/Cookies")
            if os.path.exists(edge_path):
                return edge_path
        elif self.system == "Linux":
            edge_path = os.path.expanduser("~/.config/microsoft-edge/Default/Cookies")
            if os.path.exists(edge_path):
                return edge_path
        return None

    def get_firefox_cookies_path(self):
        """Firefox cookies dosyasının yolunu bulur"""
        if self.system == "Windows":
            firefox_path = os.path.expanduser("~\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles")
        elif self.system == "Darwin":  # macOS
            firefox_path = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        elif self.system == "Linux":
            firefox_path = os.path.expanduser("~/.mozilla/firefox")
        else:
            return None
            
        if os.path.exists(firefox_path):
            profiles = [d for d in os.listdir(firefox_path) if d.endswith('.default') or d.endswith('.default-release')]
            if profiles:
                cookies_path = os.path.join(firefox_path, profiles[0], "cookies.sqlite")
                if os.path.exists(cookies_path):
                    return cookies_path
        return None

    def decrypt_chrome_cookies(self, encrypted_value):
        """Chrome/Edge cookies'lerini şifre çözer"""
        try:
            if self.system == "Windows" and WINDOWS_CRYPT_AVAILABLE:
                # Windows için DPAPI kullanarak şifre çözme
                decrypted = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)
                return decrypted.decode('utf-8')
            else:
                # Şifre çözme yapılamıyorsa None döndür
                return None
        except Exception as e:
            print(f"Cookie şifre çözme hatası: {e}")
            return None

    def extract_chrome_cookies(self):
        log_event("Chrome cookie extraction process started.")
        cookies_path = self.get_chrome_cookies_path()
        if not cookies_path:
            log_event("Chrome cookies file not found!")
            print("Chrome cookies file not found!")
            return False
            
        try:
            # Cookies dosyasının kopyasını oluştur (Chrome açikken erişim sorunu olabilir)
            temp_cookies_path = tempfile.mktemp(suffix='.db')
            shutil.copy2(cookies_path, temp_cookies_path)
            log_event(f"Chrome cookies file copied: {temp_cookies_path}")
            
            conn = sqlite3.connect(temp_cookies_path)
            cursor = conn.cursor()
            
            # YouTube cookies'lerini al
            cursor.execute("""
                SELECT name, value, host_key, path, expires_utc, is_secure
                FROM cookies 
                WHERE host_key LIKE '%youtube.com' OR host_key LIKE '%.youtube.com'
                ORDER BY host_key, name
            """)
            
            cookies = cursor.fetchall()
            conn.close()
            
            # Geçici dosyayı sil
            try:
                os.unlink(temp_cookies_path)
            except:
                pass  # Geçici dosya silinemezse sorun değil
            
            if not cookies:
                log_event("Chrome: YouTube cookies not found!")
                print("YouTube cookies not found!")
                return False
                
            # Netscape formatında cookies dosyası oluştur
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file was generated by YouTube Downloader\n")
                f.write("# Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
                
                for name, value, host_key, path, expires_utc, is_secure in cookies:
                    # expires_utc'yi Unix timestamp'e çevir
                    if expires_utc:
                        expires = expires_utc / 1000000 - 11644473600
                    else:
                        expires = 0
                    
                    # Netscape format: domain, domain_specified, path, secure, expiration, name, value
                    f.write(f"{host_key}\tTRUE\t{path}\t{'TRUE' if is_secure else 'FALSE'}\t{int(expires)}\t{name}\t{value}\n")
            
            log_event(f"Chrome'dan {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            print(f"Chrome'dan {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            return True
            
        except Exception as e:
            log_event(f"Chrome cookies extraction error: {e}")
            print(f"Chrome cookies extraction error: {e}")
            return False

    def extract_edge_cookies(self):
        log_event("Edge cookie extraction process started.")
        cookies_path = self.get_edge_cookies_path()
        if not cookies_path:
            log_event("Edge cookies file not found!")
            print("Edge cookies file not found!")
            return False
            
        try:
            # Cookies dosyasının kopyasını oluştur (Edge açikken erişim sorunu olabilir)
            temp_cookies_path = tempfile.mktemp(suffix='.db')
            
            # Edge açıkken dosyayı kopyalamaya çalış
            try:
                shutil.copy2(cookies_path, temp_cookies_path)
                log_event(f"Edge cookies file copied: {temp_cookies_path}")
            except PermissionError:
                log_event("Edge cookies file is not accessible (PermissionError). Is the browser closed?")
                print("Edge is open, cannot access cookies file.")
                return False
                
                # Tekrar kopyalamayı dene
                try:
                    shutil.copy2(cookies_path, temp_cookies_path)
                except PermissionError:
                    print("Still cannot access the file. Please close Edge and try again.")
                    return False
            
            conn = sqlite3.connect(temp_cookies_path)
            cursor = conn.cursor()
            
            # YouTube cookies'lerini al
            cursor.execute("""
                SELECT name, value, host_key, path, expires_utc, is_secure
                FROM cookies 
                WHERE host_key LIKE '%youtube.com' OR host_key LIKE '%.youtube.com'
                ORDER BY host_key, name
            """)
            
            cookies = cursor.fetchall()
            conn.close()
            
            # Geçici dosyayı sil
            try:
                os.unlink(temp_cookies_path)
            except:
                pass  # Geçici dosya silinemezse sorun değil
            
            if not cookies:
                log_event("Edge: YouTube cookies not found!")
                print("YouTube cookies not found!")
                return False
                
            # Netscape formatında cookies dosyası oluştur
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file was generated by YouTube Downloader\n")
                f.write("# Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
                
                for name, value, host_key, path, expires_utc, is_secure in cookies:
                    # expires_utc'yi Unix timestamp'e çevir
                    if expires_utc:
                        expires = expires_utc / 1000000 - 11644473600
                    else:
                        expires = 0
                    
                    # Netscape format: domain, domain_specified, path, secure, expiration, name, value
                    f.write(f"{host_key}\tTRUE\t{path}\t{'TRUE' if is_secure else 'FALSE'}\t{int(expires)}\t{name}\t{value}\n")
            
            log_event(f"Edge'den {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            print(f"Edge'den {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            return True
            
        except Exception as e:
            log_event(f"Edge cookies extraction error: {e}")
            print(f"Edge cookies extraction error: {e}")
            return False

    def extract_firefox_cookies(self):
        log_event("Firefox cookie extraction process started.")
        cookies_path = self.get_firefox_cookies_path()
        if not cookies_path:
            log_event("Firefox cookies file not found!")
            print("Firefox cookies file not found!")
            return False
            
        try:
            # Cookies dosyasının kopyasını oluştur
            temp_cookies_path = tempfile.mktemp(suffix='.db')
            shutil.copy2(cookies_path, temp_cookies_path)
            log_event(f"Firefox cookies file copied: {temp_cookies_path}")
            
            conn = sqlite3.connect(temp_cookies_path)
            cursor = conn.cursor()
            
            # YouTube cookies'lerini al
            cursor.execute("""
                SELECT name, value, host, path, expiry, isSecure
                FROM moz_cookies 
                WHERE host LIKE '%youtube.com' OR host LIKE '%.youtube.com'
                ORDER BY host, name
            """)
            
            cookies = cursor.fetchall()
            conn.close()
            
            # Geçici dosyayı sil
            try:
                os.unlink(temp_cookies_path)
            except:
                pass  # Geçici dosya silinemezse sorun değil
            
            if not cookies:
                log_event("Firefox: YouTube cookies not found!")
                print("YouTube cookies not found!")
                return False
                
            # Netscape formatında cookies dosyası oluştur
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file was generated by YouTube Downloader\n")
                f.write("# Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
                
                for name, value, host, path, expiry, is_secure in cookies:
                    # Netscape format: domain, domain_specified, path, secure, expiration, name, value
                    f.write(f"{host}\tTRUE\t{path}\t{'TRUE' if is_secure else 'FALSE'}\t{expiry}\t{name}\t{value}\n")
            
            log_event(f"Firefox'tan {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            print(f"Firefox'tan {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            return True
            
        except Exception as e:
            log_event(f"Firefox cookies extraction error: {e}")
            print(f"Firefox cookies extraction error: {e}")
            return False

    def extract_cookies(self, browser="auto"):
        log_event(f"extract_cookies called: browser={browser}")
        print("YouTube cookies are being extracted...")
        
        if browser.lower() == "chrome":
            return self.extract_chrome_cookies()
        elif browser.lower() == "edge":
            return self.extract_edge_cookies()
        elif browser.lower() == "firefox":
            return self.extract_firefox_cookies()
        elif browser.lower() == "auto":
            # Önce Edge'i dene, sonra Chrome'u, sonra Firefox'u
            if self.extract_edge_cookies():
                return True
            elif self.extract_chrome_cookies():
                return True
            elif self.extract_firefox_cookies():
                return True
            else:
                log_event("No cookies found from any browser.")
                print("No cookies found from any browser.")
                return False
        else:
            log_event(f"Invalid browser selection: {browser}")
            print("Invalid browser selection! Use 'chrome', 'edge', 'firefox' or 'auto'.")
            return False

    def get_cookies_file_path(self):
        """Returns the full path of the generated cookies file"""
        return os.path.abspath(self.output_file)

def main():
    parser = argparse.ArgumentParser(description='YouTube Cookies Extractor')
    parser.add_argument('--browser', choices=['chrome', 'edge', 'firefox', 'auto'], default='auto',
                       help='Browser selection (default: auto)')
    parser.add_argument('--output', default='youtube_cookies.txt',
                       help='Output file name (default: youtube_cookies.txt)')
    parser.add_argument('--auto', action='store_true', help='Automatic browser selection (Edge -> Chrome -> Firefox)')
    
    args = parser.parse_args()
    
    extractor = CookieExtractor()
    extractor.output_file = args.output
    
    # --auto parametresi verilmişse browser'ı auto yap
    if args.auto:
        browser = 'auto'
    else:
        browser = args.browser
    
    success = extractor.extract_cookies(browser)
    
    if success:
        cookies_path = extractor.get_cookies_file_path()
        log_event(f"Cookies successfully extracted: {cookies_path}")
        print(f"Cookies successfully extracted: {cookies_path}")
        return 0
    else:
        log_event("Cookies could not be extracted!")
        print("Cookies could not be extracted!")
        return 1

if __name__ == "__main__":
    # Komut satırı argümanları yoksa interaktif mod
    if len(sys.argv) == 1:
        extractor = CookieExtractor()
        
        print("=== YouTube Cookies Extractor ===")
        print("1. Extract cookies from Edge")
        print("2. Extract cookies from Chrome")
        print("3. Extract cookies from Firefox")
        print("4. Automatic (Edge -> Chrome -> Firefox)")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == "1":
            success = extractor.extract_cookies("edge")
        elif choice == "2":
            success = extractor.extract_cookies("chrome")
        elif choice == "3":
            success = extractor.extract_cookies("firefox")
        elif choice == "4":
            success = extractor.extract_cookies("auto")
        elif choice == "5":
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid choice!")
            sys.exit(1)
        
        if success:
            cookies_path = extractor.get_cookies_file_path()
            print(f"\nCookies successfully extracted!")
            print(f"File location: {cookies_path}")
            print("\nYou can use this file in the YouTube Downloader application.")
        else:
            print("\nCookies could not be extracted!")
            print("Please:")
            print("- Ensure you are logged into YouTube in your browser")
            print("- Close your browser and try again")
            print("- Try exporting cookies manually")
    else:
        # Komut satırı argümanları varsa normal main() çalıştır
        sys.exit(main()) 