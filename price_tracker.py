# -*- coding: utf-8 -*-
"""
Shell Motorin Fiyat Takip
Lokasyonlar: İstanbul Anadolu (Tuzla), Aksaray Merkez, Ankara Etimesgut
"""

from dotenv import load_dotenv
load_dotenv()

import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import os
from datetime import datetime, timedelta, timezone
import smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Sütun sırası ve lokasyon tanımları
SUTUNLAR = ['tarih', 'istanbul_anadolu', 'aksaray', 'ankara']

LOKASYONLAR = {
    'istanbul_anadolu': {
        'url_path': 'istanbul-anadolu/tuzla',
        'adi': 'İstanbul Anadolu (Tuzla)',
        'email_env': 'EMAIL_RECEIVER_ISTANBUL',
    },
    'aksaray': {
        'url_path': 'aksaray/merkez',
        'adi': 'Aksaray Merkez',
        'email_env': 'EMAIL_RECEIVER_AKSARAY',
    },
    'ankara': {
        'url_path': 'ankara/etimesgut',
        'adi': 'Ankara Etimesgut',
        'email_env': 'EMAIL_RECEIVER_ANKARA',
    },
}


class YakitFiyatTakip:
    def __init__(self):
        self.workspace = os.getenv('GITHUB_WORKSPACE', os.getcwd())
        self.veri_dosyasi = os.path.join(self.workspace, 'motorin_fiyatlari.csv')
        self.driver = None

    # ── Veri ────────────────────────────────────────────────────────────────

    def verileri_yukle(self):
        if not os.path.exists(self.veri_dosyasi):
            return pd.DataFrame(columns=SUTUNLAR)
        try:
            df = pd.read_csv(self.veri_dosyasi)
            # Eski format: 'fiyat' sütununu 'istanbul_anadolu' olarak migrate et
            if 'fiyat' in df.columns and 'istanbul_anadolu' not in df.columns:
                df = df.rename(columns={'fiyat': 'istanbul_anadolu'})
                print("✓ CSV migrate edildi: 'fiyat' → 'istanbul_anadolu'")
            # Yeni sütunları yoksa ekle
            for sutun in SUTUNLAR:
                if sutun not in df.columns:
                    df[sutun] = None
            return df[SUTUNLAR]
        except Exception as e:
            print(f"✗ Veri yükleme hatası: {e}")
            return pd.DataFrame(columns=SUTUNLAR)

    def veri_guncelle(self, tarih, lokasyon, fiyat):
        df = self.verileri_yukle()
        if tarih in df['tarih'].values:
            df.loc[df['tarih'] == tarih, lokasyon] = fiyat
        else:
            yeni_satir = {k: None for k in SUTUNLAR}
            yeni_satir['tarih'] = tarih
            yeni_satir[lokasyon] = fiyat
            df = pd.concat([df, pd.DataFrame([yeni_satir])], ignore_index=True)
        df = df.sort_values('tarih', ascending=True).reset_index(drop=True)
        df.to_csv(self.veri_dosyasi, index=False)
        return df

    # ── Selenium ─────────────────────────────────────────────────────────────

    def setup_driver(self):
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
        )
        self.driver = webdriver.Chrome(service=Service(), options=options)
        print("✓ WebDriver başlatıldı")

    def close_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def fiyat_cek(self, lokasyon_key):
        url = f"https://www.doviz.com/akaryakit-fiyatlari/{LOKASYONLAR[lokasyon_key]['url_path']}/shell"
        print(f"→ {LOKASYONLAR[lokasyon_key]['adi']} fiyatı çekiliyor...")
        self.driver.get(url)
        wait = WebDriverWait(self.driver, 30)
        fiyat_elements = wait.until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "td.text-bold.p-12.text-center")
            )
        )
        if len(fiyat_elements) < 2:
            raise Exception("Motorin fiyat elementi bulunamadı")
        motorin_str = fiyat_elements[1].text.strip()
        fiyat = float(motorin_str.replace('₺', '').replace(',', '.'))
        print(f"✓ {LOKASYONLAR[lokasyon_key]['adi']}: {fiyat:.2f} ₺")
        return fiyat

    # ── Rapor ────────────────────────────────────────────────────────────────

    def istatistik_hesapla(self, df, lokasyon, gun_sayisi):
        veri = df[df[lokasyon].notna()][['tarih', lokasyon]]
        if len(veri) == 0:
            return None
        son = veri.tail(gun_sayisi)
        fiyatlar = son[lokasyon].tolist()
        return {
            'ortalama': round(sum(fiyatlar) / len(fiyatlar), 2),
            'en_yuksek': round(max(fiyatlar), 2),
            'en_dusuk': round(min(fiyatlar), 2),
            'gun_sayisi': len(fiyatlar),
            'baslangic_tarih': son.iloc[0]['tarih'],
            'bitis_tarih': son.iloc[-1]['tarih'],
        }

    def rapor_olustur(self, lokasyon_key, guncel_fiyat, df, tr_time):
        lokasyon_adi = LOKASYONLAR[lokasyon_key]['adi']
        haftalik = self.istatistik_hesapla(df, lokasyon_key, 7)
        aylik = self.istatistik_hesapla(df, lokasyon_key, 30)
        toplam_gun = int(df[lokasyon_key].notna().sum())

        if haftalik is None:
            haftalik = {
                'ortalama': guncel_fiyat, 'en_yuksek': guncel_fiyat, 'en_dusuk': guncel_fiyat,
                'gun_sayisi': 1,
                'baslangic_tarih': tr_time.strftime('%Y-%m-%d'),
                'bitis_tarih': tr_time.strftime('%Y-%m-%d'),
            }
        if aylik is None:
            aylik = haftalik.copy()

        def ozet_tablo(istat, etiket, guncel):
            yuzde = 'haftalık' if etiket == 'haftalık' else 'aylık'
            return f"""
                <h2 style="color: #333; margin-top: 40px;">📊 Son {istat['gun_sayisi']} Günlük Özet ({etiket})</h2>
                <p style="color: #666; margin-top: -15px; font-size: 14px;">
                    {istat['baslangic_tarih']} - {istat['bitis_tarih']}
                </p>
                <div style="background: linear-gradient(to right, #f5f5f5, #e8e8e8); padding: 20px; border-radius: 8px; margin: 15px 0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">Ortalama:</td>
                            <td style="padding: 8px; text-align: right;">{istat['ortalama']:.2f} ₺</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">En Yüksek:</td>
                            <td style="padding: 8px; text-align: right; color: #d32f2f;">{istat['en_yuksek']:.2f} ₺</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; font-weight: bold;">En Düşük:</td>
                            <td style="padding: 8px; text-align: right; color: #388e3c;">{istat['en_dusuk']:.2f} ₺</td>
                        </tr>
                    </table>
                    <p style="margin: 15px 0 0 0; padding-top: 15px; border-top: 1px solid #ddd; color: #666; font-size: 14px;">
                        {'📈' if guncel > istat['ortalama'] else '📉'}
                        Bugünkü fiyat {yuzde} ortalamaya göre
                        <strong style="color: {'#d32f2f' if guncel > istat['ortalama'] else '#388e3c'};">
                            {guncel - istat['ortalama']:+.2f} ₺
                        </strong>
                    </p>
                </div>"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: #DD1D21; color: white; padding: 20px; border-radius: 5px;">
                <h1 style="margin: 0;">🔔 Shell Motorin Fiyat Raporu</h1>
                <p style="margin: 10px 0 0 0;">{lokasyon_adi} — {tr_time.strftime('%d.%m.%Y %H:%M:%S')}</p>
            </div>
            <div style="padding: 20px;">
                <h2 style="color: #333;">Güncel Fiyat</h2>
                <div style="font-size: 48px; font-weight: bold; color: #DD1D21; margin: 20px 0;">
                    {guncel_fiyat:.2f} ₺/Lt
                </div>
                {ozet_tablo(haftalik, 'haftalık', guncel_fiyat)}
                {ozet_tablo(aylik, 'aylık', guncel_fiyat)}
                <div style="margin-top: 40px; padding: 15px; background-color: #f9f9f9; border-left: 4px solid #DD1D21; border-radius: 4px;">
                    <p style="margin: 0; color: #666; font-size: 13px;">
                        📅 <strong>{toplam_gun}</strong> gündür takip ediliyor<br>
                        🤖 GitHub Actions — Her gün 00:00 TR saatinde güncellenir.
                    </p>
                </div>
            </div>
        </body>
        </html>"""
        return html

    # ── Email ────────────────────────────────────────────────────────────────

    def email_gonder(self, icerik, alici, tr_time):
        email_gonderen = os.getenv('EMAIL_SENDER')
        email_sifre = os.getenv('SMTP_KEY')
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))

        if not all([email_gonderen, email_sifre, alici]):
            raise ValueError("Email bilgileri eksik (EMAIL_SENDER, SMTP_KEY veya alıcı tanımlı değil)")

        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🔔 Shell Motorin Fiyatı — {tr_time.strftime('%d.%m.%Y %H:%M:%S')}"
        msg['From'] = email_gonderen
        msg['To'] = alici
        msg.attach(MIMEText(icerik, 'html', 'utf-8'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        try:
            server.starttls()
            server.login(email_gonderen, email_sifre)
            server.send_message(msg)
            print(f"✓ Email gönderildi → {alici}")
        finally:
            try:
                server.quit()
            except Exception:
                pass

    # ── Ana Döngü ────────────────────────────────────────────────────────────

    def calistir(self):
        print("\n" + "=" * 42)
        print("  🚗 SHELL YAKIT FİYAT TAKİP")
        print("=" * 42 + "\n")

        tr_time = datetime.now(timezone.utc) + timedelta(hours=3)
        bugun = tr_time.strftime('%Y-%m-%d')
        hatalar = []

        try:
            self.setup_driver()

            for lokasyon_key, lokasyon_info in LOKASYONLAR.items():
                print(f"\n── {lokasyon_info['adi']} ──")
                try:
                    fiyat = self.fiyat_cek(lokasyon_key)
                    df = self.veri_guncelle(bugun, lokasyon_key, fiyat)

                    alici = os.getenv(lokasyon_info['email_env'])
                    if alici:
                        rapor = self.rapor_olustur(lokasyon_key, fiyat, df, tr_time)
                        self.email_gonder(rapor, alici, tr_time)
                    else:
                        print(f"⚠ Alıcı tanımlı değil ({lokasyon_info['email_env']}), email atlandı")

                except Exception as e:
                    print(f"✗ Hata: {e}")
                    try:
                        path = os.path.join(self.workspace, f"hata_screenshot_{lokasyon_key}.png")
                        self.driver.save_screenshot(path)
                        print(f"→ Screenshot kaydedildi: {path}")
                    except Exception:
                        pass
                    hatalar.append(lokasyon_info['adi'])
        finally:
            self.close_driver()

        print("\n" + "=" * 42)
        if hatalar:
            print(f"  ⚠ Hatalı lokasyonlar: {', '.join(hatalar)}")
            return 1
        print("  ✅ Tüm lokasyonlar başarıyla tamamlandı")
        return 0


if __name__ == "__main__":
    sys.exit(YakitFiyatTakip().calistir())
