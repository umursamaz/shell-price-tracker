#!/usr/bin/env python3
"""
Shell Yakıt Fiyat Takip Scripti - GitHub Actions Versiyonu
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import json
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import statistics

# GitHub Actions'da çalışacak şekilde ayarlanmış
class YakitFiyatTakip:
    def __init__(self):
        self.veri_dosyasi = 'fiyat_verileri.json'
        self.veriler = self.verileri_yukle()
        self.driver = None
    
    def verileri_yukle(self):
        if os.path.exists(self.veri_dosyasi):
            try:
                with open(self.veri_dosyasi, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def verileri_kaydet(self):
        with open(self.veri_dosyasi, 'w', encoding='utf-8') as f:
            json.dump(self.veriler, f, ensure_ascii=False, indent=2)
        print("✓ Veriler kaydedildi")
    
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        print("✓ WebDriver başlatıldı")
    
    def close_driver(self):
        if self.driver:
            self.driver.quit()
    
    def fiyat_cek(self):
        try:
            self.setup_driver()
            
            print("→ Sayfa yükleniyor...")
            self.driver.get('https://www.shell.com.tr/suruculer/shell-yakitlari/akaryakit-pompa-satis-fiyatlari.html')
            
            wait = WebDriverWait(self.driver, 20)
            
            print("→ İstanbul seçiliyor...")
            il_dropdown = wait.until(EC.element_to_be_clickable((By.ID, "cb_all_cb_province_I")))
            il_dropdown.click()
            time.sleep(1)
            
            istanbul = wait.until(EC.element_to_be_clickable((By.XPATH, "//td[contains(text(), 'ISTANBUL')]")))
            istanbul.click()
            time.sleep(2)
            
            print("→ Tuzla seçiliyor...")
            ilce_dropdown = wait.until(EC.visibility_of_element_located((By.ID, "cb_all_cb_county_I")))
            ilce_dropdown.click()
            time.sleep(1)
            
            tuzla = wait.until(EC.element_to_be_clickable((By.XPATH, "//td[contains(text(), 'TUZLA')]")))
            tuzla.click()
            time.sleep(2)
            
            wait.until(EC.presence_of_element_located((By.ID, "cb_all_grdPrices")))
            
            tuzla_row = self.driver.find_element(By.XPATH, "//td[contains(text(), 'TUZLA')]/parent::tr")
            motorin_cell = tuzla_row.find_elements(By.TAG_NAME, "td")[2]
            motorin_str = motorin_cell.text.strip()
            motorin_fiyat = float(motorin_str.replace(',', '.'))
            
            print(f"✓ Fiyat çekildi: {motorin_fiyat} ₺")
            return motorin_fiyat
            
        except Exception as e:
            print(f"✗ Hata: {e}")
            return None
        finally:
            self.close_driver()
    
    def istatistik_hesapla(self, gun_sayisi):
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
        bugun = datetime.now().strftime('%d.%m.%Y')
        toplam_gun = len(self.veriler)
        
        haftalik = self.istatistik_hesapla(min(7, toplam_gun))
        aylik = self.istatistik_hesapla(min(30, toplam_gun))
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: #DD1D21; color: white; padding: 20px;">
                <h1>🔔 Shell Motorin Fiyat Raporu</h1>
                <p>İstanbul / Tuzla - {bugun}</p>
                <p style="font-size:12px;">🤖 GitHub Actions tarafından otomatik gönderildi</p>
            </div>
            <div style="padding: 20px;">
                <h2>Güncel Fiyat</h2>
                <div style="font-size: 36px; font-weight: bold; color: #DD1D21;">
                    {guncel_fiyat:.2f} ₺/Litre
                </div>
                
                <h2>Son {haftalik['gun_sayisi']} Günlük Özet</h2>
                <div style="background-color: #f5f5f5; padding: 15px; margin: 10px 0;">
                    <p><b>Ortalama:</b> {haftalik['ortalama']:.2f} ₺</p>
                    <p><b>En Yüksek:</b> {haftalik['en_yuksek']:.2f} ₺</p>
                    <p><b>En Düşük:</b> {haftalik['en_dusuk']:.2f} ₺</p>
                    <p style="color: #666;">Fark: {guncel_fiyat - haftalik['ortalama']:+.2f} ₺</p>
                </div>
                
                <h2>Son {aylik['gun_sayisi']} Günlük Özet</h2>
                <div style="background-color: #f5f5f5; padding: 15px; margin: 10px 0;">
                    <p><b>Ortalama:</b> {aylik['ortalama']:.2f} ₺</p>
                    <p><b>En Yüksek:</b> {aylik['en_yuksek']:.2f} ₺</p>
                    <p><b>En Düşük:</b> {aylik['en_dusuk']:.2f} ₺</p>
                    <p style="color: #666;">Fark: {guncel_fiyat - aylik['ortalama']:+.2f} ₺</p>
                </div>
                
                <p style="margin-top: 30px; color: #666; font-size: 12px;">
                    Toplam {toplam_gun} gündür takip ediliyor.
                </p>
            </div>
        </body>
        </html>
        """
        return html
    
    def email_gonder(self, icerik):
        email_gonderen = os.environ.get('EMAIL_SENDER', 'osmankara@sabanciuniv.edu')
        email_sifre = os.environ.get('SMTP_KEY')
        email_alici = os.environ.get('EMAIL_RECEIVER', 'osmankara@sabanciuniv.edu')
        
        if not email_sifre:
            print("✗ SMTP_KEY environment variable bulunamadı!")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Shell Motorin - {datetime.now().strftime('%d.%m.%Y')}"
            msg['From'] = email_gonderen
            msg['To'] = email_alici
            
            msg.attach(MIMEText(icerik, 'html', 'utf-8'))
            
            server = smtplib.SMTP('smtp-relay.brevo.com', 587)
            server.starttls()
            server.login(email_gonderen, email_sifre)
            server.send_message(msg)
            server.quit()
            
            print("✓ Email gönderildi")
            return True
        except Exception as e:
            print(f"✗ Email hatası: {e}")
            return False
    
    def calistir(self):
        print("\n" + "="*50)
        print("SHELL YAKIT FİYAT TAKİP - GitHub Actions")
        print("="*50 + "\n")
        
        fiyat = self.fiyat_cek()
        
        if fiyat is None:
            print("✗ Fiyat çekilemedi!")
            return
        
        bugun = datetime.now().date().isoformat()
        self.veriler[bugun] = fiyat
        self.verileri_kaydet()
        
        rapor = self.rapor_olustur(fiyat)
        self.email_gonder(rapor)
        
        print(f"\n✓ Tamamlandı! Fiyat: {fiyat:.2f} ₺\n")

if __name__ == "__main__":
    takip = YakitFiyatTakip()
    takip.calistir()
