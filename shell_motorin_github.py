# -*- coding: utf-8 -*-
"""
Shell Motorin Fiyat Takip (GitHub Actions Version)
"""

import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import json
import os
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import statistics

class YakitFiyatTakip:
    def __init__(self):
        # GitHub workspace path
        self.workspace = os.getenv('GITHUB_WORKSPACE', os.getcwd())
        self.veri_dosyasi = os.path.join(self.workspace, 'fiyat_verileri.json')
        self.screenshot_path = os.path.join(self.workspace, 'hata_screenshot.png')
        self.veriler = self.verileri_yukle()
        self.driver = None
        self.wait_timeout = 30
    
    def verileri_yukle(self):
        """JSON dosyasından verileri yükle"""
        if os.path.exists(self.veri_dosyasi):
            try:
                with open(self.veri_dosyasi, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Veri yükleme hatası: {e}")
                return {}
        return {}
    
    def verileri_kaydet(self):
        """Verileri JSON dosyasına kaydet"""
        try:
            with open(self.veri_dosyasi, 'w', encoding='utf-8') as f:
                json.dump(self.veriler, f, ensure_ascii=False, indent=2)
            print("✓ Veriler kaydedildi")
        except Exception as e:
            print(f"✗ Veri kaydetme hatası: {e}")
    
    def setup_driver(self):
        """Selenium WebDriver'ı başlat (GitHub Actions için özelleştirilmiş)"""
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            
            chrome_options = Options()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            print("✓ WebDriver başlatıldı")
        except Exception as e:
            print(f"✗ WebDriver başlatma hatası: {e}")
            raise
    
    def close_driver(self):
        """WebDriver'ı kapat"""
        if self.driver:
            self.driver.quit()
    
    def fiyat_cek(self):
        """Doviz.com sitesinden fiyat çek"""
        try:
            self.setup_driver()
            
            print("→ Sayfa yükleniyor...")
            self.driver.get('https://www.doviz.com/akaryakit-fiyatlari/istanbul-anadolu/tuzla/shell')
            
            wait = WebDriverWait(self.driver, self.wait_timeout)
            
            print("→ Fiyat elementi bekleniyor...")
            fiyat_elements = wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "td.text-bold.p-12.text-center")
                )
            )
            
            if len(fiyat_elements) < 2:
                raise Exception("Fiyat elementi bulunamadı")
            
            motorin_element = fiyat_elements[1]
            motorin_str = motorin_element.text.strip()
            motorin_fiyat = float(motorin_str.replace('₺', '').replace(',', '.'))
            
            print(f"✓ Fiyat başarıyla çekildi: {motorin_fiyat} ₺")
            return motorin_fiyat
            
        except Exception as e:
            print(f"✗ Fiyat çekme hatası: {e}")
            try:
                os.makedirs(os.path.dirname(self.screenshot_path), exist_ok=True)
                self.driver.save_screenshot(self.screenshot_path)
                print(f"→ Screenshot kaydedildi: {self.screenshot_path}")
            except Exception as screenshot_error:
                print(f"✗ Screenshot kaydetme hatası: {screenshot_error}")
            raise
        finally:
            self.close_driver()

    def istatistik_hesapla(self, gun_sayisi):
        """İstatistik hesapla"""
        tarihler = sorted(self.veriler.keys(), reverse=True)
        ilgili_fiyatlar = [self.veriler[t] for i, t in enumerate(tarihler) if i < gun_sayisi]
        
        if not ilgili_fiyatlar:
            return None
        
        return {
            'ortalama': round(statistics.mean(ilgili_fiyatlar), 2),
            'en_yuksek': round(max(ilgili_fiyatlar), 2),
            'en_dusuk': round(min(ilgili_fiyatlar), 2),
            'gun_sayisi': len(ilgili_fiyatlar)
        }
    
    def rapor_olustur(self, guncel_fiyat):
        """HTML rapor oluştur"""
        # UTC'den Türkiye saatine çevir (UTC+3)
        tr_time = datetime.now() + timedelta(hours=3)
        bugun = tr_time.strftime('%d.%m.%Y')
        toplam_gun = len(self.veriler)
        
        haftalik = self.istatistik_hesapla(min(7, toplam_gun))
        aylik = self.istatistik_hesapla(min(30, toplam_gun))
        
        if not haftalik or not aylik:
            haftalik = {'ortalama': guncel_fiyat, 'en_yuksek': guncel_fiyat, 
                       'en_dusuk': guncel_fiyat, 'gun_sayisi': 1}
            aylik = haftalik.copy()
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: #DD1D21; color: white; padding: 20px; border-radius: 5px;">
                <h1 style="margin: 0;">🔔 Shell Motorin Fiyat Raporu</h1>
                <p style="margin: 10px 0 0 0;">İstanbul / Tuzla - {tr_time.strftime('%d.%m.%Y %H:%M:%S')}</p>
                <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.9;">🤖 GitHub Actions tarafından otomatik oluşturuldu</p>
            </div>
            
            <div style="padding: 20px;">
                <h2 style="color: #333;">Güncel Fiyat</h2>
                <div style="font-size: 48px; font-weight: bold; color: #DD1D21; margin: 20px 0;">
                    {guncel_fiyat:.2f} ₺/Lt
                </div>
                
                <h2 style="color: #333; margin-top: 40px;">📊 Son {haftalik['gun_sayisi']} Günlük Özet</h2>
                <div style="background: linear-gradient(to right, #f5f5f5, #e8e8e8); padding: 20px; border-radius: 8px; margin: 15px 0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">Ortalama:</td>
                            <td style="padding: 8px; text-align: right;">{haftalik['ortalama']:.2f} ₺</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">En Yüksek:</td>
                            <td style="padding: 8px; text-align: right; color: #d32f2f;">{haftalik['en_yuksek']:.2f} ₺</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">En Düşük:</td>
                            <td style="padding: 8px; text-align: right; color: #388e3c;">{haftalik['en_dusuk']:.2f} ₺</td>
                        </tr>
                    </table>
                    <p style="margin: 15px 0 0 0; padding-top: 15px; border-top: 1px solid #ddd; color: #666; font-size: 14px;">
                        {'📈' if guncel_fiyat > haftalik['ortalama'] else '📉'} 
                        Bugünkü fiyat haftalık ortalamaya göre 
                        <strong style="color: {'#d32f2f' if guncel_fiyat > haftalik['ortalama'] else '#388e3c'};">
                            {guncel_fiyat - haftalik['ortalama']:+.2f} ₺
                        </strong>
                    </p>
                </div>
                
                <h2 style="color: #333; margin-top: 40px;">📊 Son {aylik['gun_sayisi']} Günlük Özet</h2>
                <div style="background: linear-gradient(to right, #f5f5f5, #e8e8e8); padding: 20px; border-radius: 8px; margin: 15px 0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">Ortalama:</td>
                            <td style="padding: 8px; text-align: right;">{aylik['ortalama']:.2f} ₺</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">En Yüksek:</td>
                            <td style="padding: 8px; text-align: right; color: #d32f2f;">{aylik['en_yuksek']:.2f} ₺</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">En Düşük:</td>
                            <td style="padding: 8px; text-align: right; color: #388e3c;">{aylik['en_dusuk']:.2f} ₺</td>
                        </tr>
                    </table>
                    <p style="margin: 15px 0 0 0; padding-top: 15px; border-top: 1px solid #ddd; color: #666; font-size: 14px;">
                        {'📈' if guncel_fiyat > aylik['ortalama'] else '📉'} 
                        Bugünkü fiyat aylık ortalamaya göre 
                        <strong style="color: {'#d32f2f' if guncel_fiyat > aylik['ortalama'] else '#388e3c'};">
                            {guncel_fiyat - aylik['ortalama']:+.2f} ₺
                        </strong>
                    </p>
                </div>
                
                <div style="margin-top: 40px; padding: 15px; background-color: #f9f9f9; border-left: 4px solid #DD1D21; border-radius: 4px;">
                    <p style="margin: 0; color: #666; font-size: 13px;">
                        📅 <strong>{toplam_gun}</strong> gündür takip ediliyor<br>
                        🤖 GitHub Actions - Her gün 00:00'da güncellenir
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def email_gonder(self, icerik):
        """Email gönder"""
        try:
            email_gonderen = os.getenv('EMAIL_SENDER')
            email_sifre = os.getenv('SMTP_KEY')
            email_alici = os.getenv('EMAIL_RECEIVER')
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            
            if not all([email_gonderen, email_sifre, email_alici]):
                print("✗ Email bilgileri eksik!")
                print(f"  Sender: {'✓' if email_gonderen else '✗'}")
                print(f"  Password: {'✓' if email_sifre else '✗'}")
                print(f"  Receiver: {'✓' if email_alici else '✗'}")
                raise ValueError("Email bilgileri eksik")
            
            msg = MIMEMultipart('alternative')
            # UTC'den Türkiye saatine çevir (UTC+3)
            tr_time = datetime.now() + timedelta(hours=3)
            msg['Subject'] = f"🔔 Shell Motorin Fiyatı - {tr_time.strftime('%d.%m.%Y %H:%M:%S')}"
            msg['From'] = email_gonderen
            msg['To'] = email_alici
            
            msg.attach(MIMEText(icerik, 'html', 'utf-8'))
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            try:
                server.starttls()
                server.login(email_gonderen, email_sifre)
                server.send_message(msg)
                print(f"✓ Email gönderildi → {email_alici}")
                return True
            except Exception as e:
                print(f"✗ SMTP işlem hatası: {e}")
                raise
            finally:
                try:
                    server.quit()
                except:
                    pass
        except Exception as e:
            print(f"✗ Email gönderme hatası: {e}")
            raise
    
    def calistir(self):
        """Ana çalışma fonksiyonu"""
        print("\n" + "="*60)
        print("  🚗 SHELL YAKIT FİYAT TAKİP - GitHub Actions")
        print("="*60 + "\n")
        
        try:
            fiyat = self.fiyat_cek()
            
            # UTC'den Türkiye saatine çevir (UTC+3)
            tr_time = datetime.now() + timedelta(hours=3)
            bugun = tr_time.date().isoformat()
            self.veriler[bugun] = fiyat
            self.verileri_kaydet()
            
            rapor = self.rapor_olustur(fiyat)
            self.email_gonder(rapor)
            
            print("\n" + "="*60)
            print(f"  ✅ İşlem tamamlandı!")
            print(f"  💰 Fiyat: {fiyat:.2f} ₺")
            print(f"  📧 Email: Gönderildi")
            print("="*60 + "\n")
            
            return 0
        except Exception as e:
            print(f"\n✗ Hata oluştu: {e}\n")
            return 1

if __name__ == "__main__":
    takip = YakitFiyatTakip()
    sys.exit(takip.calistir())
