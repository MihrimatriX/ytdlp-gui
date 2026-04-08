import os
import json
import base64
import sqlite3
import shutil
import tempfile
import subprocess
import platform
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from utils import log_event

try:
    import win32crypt
    WINDOWS_CRYPT_AVAILABLE = True
except ImportError:
    WINDOWS_CRYPT_AVAILABLE = False
    print("Warning: win32crypt not available. Cookie decryption may not work properly.")

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    AESGCM_AVAILABLE = True
except ImportError:
    AESGCM_AVAILABLE = False

class CookieExtractor:
    def __init__(self):
        self.system = platform.system()
        self.output_file = "youtube_cookies.txt"

    @staticmethod
    def _local_state_path_for_profile(cookies_path: str) -> Optional[str]:
        """Find Local State next to Chrome/Edge profile (Windows Network/Cookies or Default/Cookies)."""
        d = os.path.dirname(os.path.abspath(cookies_path))
        for _ in range(8):
            candidate = os.path.join(d, "Local State")
            if os.path.isfile(candidate):
                return candidate
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return None

    def _chromium_master_key(self, local_state_path: str):
        if not local_state_path or not os.path.isfile(local_state_path):
            return None
        if self.system != "Windows" or not WINDOWS_CRYPT_AVAILABLE:
            return None
        try:
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)
            enc_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
            enc_key = enc_key[5:]
            return win32crypt.CryptUnprotectData(enc_key, None, None, None, 0)[1]
        except Exception as e:
            log_event(f"Chromium master key error: {e}")
            return None

    def _decrypt_chromium_cookie_value(
        self, encrypted_value, plaintext_value, local_state_path: str
    ):
        if plaintext_value not in (None, ""):
            return str(plaintext_value)
        if encrypted_value in (None, b"", ""):
            return None
        blob = bytes(encrypted_value)
        if self.system == "Windows" and WINDOWS_CRYPT_AVAILABLE and AESGCM_AVAILABLE:
            if len(blob) > 15 and blob[:3] in (b"v10", b"v11"):
                master_key = self._chromium_master_key(local_state_path)
                if master_key:
                    try:
                        nonce = blob[3:15]
                        ciphertext = blob[15:]
                        aesgcm = AESGCM(master_key)
                        plain = aesgcm.decrypt(nonce, ciphertext, None)
                        return plain.decode("utf-8", errors="replace")
                    except Exception as e:
                        log_event(f"AES-GCM cookie decrypt failed: {e}")
        if self.system == "Windows" and WINDOWS_CRYPT_AVAILABLE:
            try:
                plain = win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1]
                return plain.decode("utf-8", errors="replace")
            except Exception:
                pass
        return None

    def _copy_cookies_db_temp(self, cookies_path: str) -> str:
        fd, temp_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        shutil.copy2(cookies_path, temp_path)
        return temp_path

    def _fetch_youtube_rows_chromium(self, cursor) -> list:
        q_modern = """
            SELECT name, value, encrypted_value, host_key, path, expires_utc, is_secure
            FROM cookies
            WHERE host_key LIKE '%youtube.com' OR host_key LIKE '%.youtube.com'
            ORDER BY host_key, name
        """
        q_legacy = """
            SELECT name, value, host_key, path, expires_utc, is_secure
            FROM cookies
            WHERE host_key LIKE '%youtube.com' OR host_key LIKE '%.youtube.com'
            ORDER BY host_key, name
        """
        try:
            cursor.execute(q_modern)
            return cursor.fetchall()
        except sqlite3.OperationalError:
            cursor.execute(q_legacy)
            return [
                (n, v, None, hk, p, eu, sec)
                for (n, v, hk, p, eu, sec) in cursor.fetchall()
            ]

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

    def extract_chrome_cookies(self):
        log_event("Chrome cookie extraction process started.")
        cookies_path = self.get_chrome_cookies_path()
        if not cookies_path:
            log_event("Chrome cookies file not found!")
            print("Chrome cookies file not found!")
            return False
            
        local_state = self._local_state_path_for_profile(cookies_path) or ""
        temp_cookies_path = None
        try:
            temp_cookies_path = self._copy_cookies_db_temp(cookies_path)
            log_event(f"Chrome cookies file copied: {temp_cookies_path}")

            conn = sqlite3.connect(temp_cookies_path)
            cursor = conn.cursor()
            rows = self._fetch_youtube_rows_chromium(cursor)
            conn.close()

            cookies = []
            for name, value, enc_val, host_key, path, expires_utc, is_secure in rows:
                plain = self._decrypt_chromium_cookie_value(enc_val, value, local_state)
                if plain is None:
                    continue
                cookies.append((name, plain, host_key, path, expires_utc, is_secure))

            if not cookies:
                log_event("Chrome: YouTube cookies not found (or could not decrypt)!")
                print(
                    "YouTube cookies not found or could not be decrypted. "
                    "On Windows use Chrome/Edge with cryptography + pywin32; on Linux/macOS use Firefox or export cookies manually."
                )
                return False

            with open(self.output_file, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file was generated by YouTube Downloader\n")
                f.write("# Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")

                for name, value, host_key, path, expires_utc, is_secure in cookies:
                    if expires_utc:
                        expires = expires_utc / 1000000 - 11644473600
                    else:
                        expires = 0
                    f.write(
                        f"{host_key}\tTRUE\t{path}\t{'TRUE' if is_secure else 'FALSE'}\t"
                        f"{int(expires)}\t{name}\t{value}\n"
                    )

            log_event(f"Chrome'dan {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            print(f"Chrome'dan {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            return True

        except Exception as e:
            log_event(f"Chrome cookies extraction error: {e}")
            print(f"Chrome cookies extraction error: {e}")
            return False
        finally:
            if temp_cookies_path and os.path.exists(temp_cookies_path):
                try:
                    os.unlink(temp_cookies_path)
                except OSError:
                    pass

    def extract_edge_cookies(self):
        log_event("Edge cookie extraction process started.")
        cookies_path = self.get_edge_cookies_path()
        if not cookies_path:
            log_event("Edge cookies file not found!")
            print("Edge cookies file not found!")
            return False

        local_state = self._local_state_path_for_profile(cookies_path) or ""
        temp_cookies_path = None
        try:
            try:
                temp_cookies_path = self._copy_cookies_db_temp(cookies_path)
            except PermissionError:
                log_event("Edge cookies file is not accessible (PermissionError). Is the browser closed?")
                print("Edge is open, cannot access cookies file. Close Edge and try again.")
                return False
            log_event(f"Edge cookies file copied: {temp_cookies_path}")

            conn = sqlite3.connect(temp_cookies_path)
            cursor = conn.cursor()
            rows = self._fetch_youtube_rows_chromium(cursor)
            conn.close()

            cookies = []
            for name, value, enc_val, host_key, path, expires_utc, is_secure in rows:
                plain = self._decrypt_chromium_cookie_value(enc_val, value, local_state)
                if plain is None:
                    continue
                cookies.append((name, plain, host_key, path, expires_utc, is_secure))

            if not cookies:
                log_event("Edge: YouTube cookies not found (or could not decrypt)!")
                print(
                    "YouTube cookies not found or could not be decrypted. "
                    "On Windows use Edge with cryptography + pywin32; on Linux/macOS use Firefox or export cookies manually."
                )
                return False

            with open(self.output_file, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file was generated by YouTube Downloader\n")
                f.write("# Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")

                for name, value, host_key, path, expires_utc, is_secure in cookies:
                    if expires_utc:
                        expires = expires_utc / 1000000 - 11644473600
                    else:
                        expires = 0
                    f.write(
                        f"{host_key}\tTRUE\t{path}\t{'TRUE' if is_secure else 'FALSE'}\t"
                        f"{int(expires)}\t{name}\t{value}\n"
                    )

            log_event(f"Edge'den {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            print(f"Edge'den {len(cookies)} YouTube cookie'si çıkarıldı: {self.output_file}")
            return True

        except Exception as e:
            log_event(f"Edge cookies extraction error: {e}")
            print(f"Edge cookies extraction error: {e}")
            return False
        finally:
            if temp_cookies_path and os.path.exists(temp_cookies_path):
                try:
                    os.unlink(temp_cookies_path)
                except OSError:
                    pass

    def extract_firefox_cookies(self):
        log_event("Firefox cookie extraction process started.")
        cookies_path = self.get_firefox_cookies_path()
        if not cookies_path:
            log_event("Firefox cookies file not found!")
            print("Firefox cookies file not found!")
            return False
            
        temp_cookies_path = None
        try:
            temp_cookies_path = self._copy_cookies_db_temp(cookies_path)
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
        finally:
            if temp_cookies_path and os.path.exists(temp_cookies_path):
                try:
                    os.unlink(temp_cookies_path)
                except OSError:
                    pass

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