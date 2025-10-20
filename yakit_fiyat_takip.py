#!/usr/bin/env python3
"""
Shell Yakıt Fiyat Takip - GitHub Actions Edition
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import json
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import statistics

class YakitFiyatTakip:
    def __init__(self):
        self.veri_dosyasi = 'fiyat_verileri.json'
        self.veriler = self.verileri_yukle()
        self.driver = None
    
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
        """Selenium WebDriver'ı başlat"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36')

        chrome_options.binary_location = '/usr/bin/chromium-browser'
        
        self.driver = webdriver.Chrome(options=chrome_options)
        print("✓ WebDriver başlatıldı")
    
    def close_driver(self):
        """WebDriver'ı kapat"""
        if self.driver:
            self.driver.quit()
    
    def fiyat_cek(self):
        """Shell sitesinden fiyat çek"""
        try:
            self.setup_driver()
            
            print("→ Sayfa yükleniyor...")
            self.driver.get('https://www.shell.com.tr/suruculer/shell-yakitlari/akaryakit-pompa-satis-fiyatlari.html')
            
            wait = WebDriverWait(self.driver, 30)
            
            print("→ İstanbul seçiliyor...")
            il_dropdown = wait.until(EC.element_to_be_clickable((By.ID, "cb_all_cb_province_I")))
            il_dropdown.click()
            time.sleep(2)
            
            istanbul = wait.until(EC.element_to_be_clickable((By.XPATH, "//td[contains(text(), 'ISTANBUL')]")))
            istanbul.click()
            time.sleep(3)
            
            print("→ Tuzla seçiliyor...")
            ilce_dropdown = wait.until(EC.visibility_of_element_located((By.ID, "cb_all_cb_county_I")))
            ilce_dropdown.click()
            time.sleep(2)
            
            tuzla = wait.until(EC.element_to_be_clickable((By.XPATH, "//td[contains(text(), 'TUZLA')]")))
            tuzla.click()
            time.sleep(3)
            
            print("→ Fiyat okunuyor...")
            wait.until(EC.presence_of_element_located((By.ID, "cb_all_grdPrices")))
            time.sleep(2)
            
            tuzla_row = self.driver.find_element(By.XPATH, "//td[contains(text(), 'TUZLA')]/parent::tr")
            motorin_cell = tuzla_row.find_elements(By.TAG_NAME, "td")[2]
            motorin_str = motorin_cell.text.strip()
            motorin_fiyat = float(motorin_str.replace(',', '.'))
            
            print(f"✓ Fiyat başarıyla çekildi: {motorin_fiyat} ₺")
            return motorin_fiyat
            
        except Exception as e:
            print(f"✗ Fiyat çekme hatası: {e}")
            try:
                self.driver.save_screenshot('hata_screenshot.png')
                print("→ Screenshot kaydedildi")
            except:
                pass
            return None
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
        bugun = datetime.now().strftime('%d.%m.%Y')
        toplam_gun = len(self.veriler)
        
        haftalik = self.istatistik_hesapla(min(7, toplam_gun))
        aylik = self.istatistik_hesapla(min(30, toplam_gun))
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: #DD1D21; color: white; padding: 20px; border-radius: 5px;">
                <h1 style="margin: 0;">🔔 Shell Motorin Fiyat Raporu</h1>
                <p style="margin: 10px 0 0 0;">İstanbul / Tuzla - {bugun}</p>
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
                        🤖 Otomatik rapor - Her gün 00:00'da güncellenir
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def email_gonder(self, icerik):
        """Email gönder"""
        email_gonderen = os.environ.get('EMAIL_SENDER')
        email_sifre = os.environ.get('SMTP_KEY')
        email_alici = os.environ.get('EMAIL_RECEIVER')
        
        if not all([email_gonderen, email_sifre, email_alici]):
            print("✗ Email bilgileri eksik!")
            print(f"  Sender: {'✓' if email_gonderen else '✗'}")
            print(f"  Password: {'✓' if email_sifre else '✗'}")
            print(f"  Receiver: {'✓' if email_alici else '✗'}")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🔔 Shell Motorin Fiyatı - {datetime.now().strftime('%d.%m.%Y')}"
            msg['From'] = email_gonderen
            msg['To'] = email_alici
            
            msg.attach(MIMEText(icerik, 'html', 'utf-8'))
            
            server = smtplib.SMTP('smtp-relay.brevo.com', 587)
            server.starttls()
            server.login(email_gonderen, email_sifre)
            server.send_message(msg)
            server.quit()
            
            print(f"✓ Email gönderildi → {email_alici}")
            return True
        except Exception as e:
            print(f"✗ Email gönderme hatası: {e}")
            return False
    
    def calistir(self):
        """Ana çalışma fonksiyonu"""
        print("\n" + "="*60)
        print("  🚗 SHELL YAKIT FİYAT TAKİP - GitHub Actions")
        print("="*60 + "\n")
        
        fiyat = self.fiyat_cek()
        
        if fiyat is None:
            print("\n✗ İşlem başarısız! Fiyat çekilemedi.\n")
            return False
        
        bugun = datetime.now().date().isoformat()
        self.veriler[bugun] = fiyat
        self.verileri_kaydet()
        
        rapor = self.rapor_olustur(fiyat)
        email_basarili = self.email_gonder(rapor)
        
        print("\n" + "="*60)
        print(f"  ✅ İşlem tamamlandı!")
        print(f"  💰 Fiyat: {fiyat:.2f} ₺")
        print(f"  📧 Email: {'Gönderildi' if email_basarili else 'Gönderilemedi'}")
        print("="*60 + "\n")
        
        return True

if __name__ == "__main__":
    takip = YakitFiyatTakip()
    success = takip.calistir()
    exit(0 if success else 1)
