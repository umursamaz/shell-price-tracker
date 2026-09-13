# -*- coding: utf-8 -*-
"""
Shell Motorin Fiyat Takip
Lokasyonlar: İstanbul Anadolu (Tuzla), Aksaray Merkez, Ankara Etimesgut

Fiyatlar Shell'in resmi fiyat panelinden alınır. Panel günün listesini sabah ~06:10 TR'de
yayınlıyor; liste henüz bugünün değilse veya panele ulaşılamazsa lokasyon bir sonraki
zamanlanmış denemeye bırakılır. Son denemede (SON_DENEME=true) de alınamazsa fiyat
doviz.com'dan alınır ve mailde uyarı gösterilir.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import re
import sys
import smtplib
import urllib.request
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

SHELL_URL = "https://pompafiyat.turkiyeshell.com/prices"
DOVIZ_URL = "https://www.doviz.com/akaryakit-fiyatlari/{}/shell"

# Sütun sırası ve lokasyon tanımları
SUTUNLAR = ['tarih', 'istanbul_anadolu', 'aksaray', 'ankara']

LOKASYONLAR = {
    'istanbul_anadolu': {
        'adi': 'İstanbul Anadolu (Tuzla)',
        'shell_il': 'ISTANBUL',
        'shell_ilce': 'TUZLA',
        'doviz_path': 'istanbul-anadolu/tuzla',
        'email_envs': [],  # Fiyatı takip edilmeye devam ediyor, mail gönderilmiyor
    },
    'aksaray': {
        'adi': 'Aksaray Merkez',
        'shell_il': 'AKSARAY',
        'shell_ilce': 'MERKEZ',
        'doviz_path': 'aksaray/merkez',
        'email_envs': ['EMAIL_RECEIVER_AKSARAY'],
    },
    'ankara': {
        'adi': 'Ankara Etimesgut',
        'shell_il': 'ANKARA',
        'shell_ilce': 'ETIMESGUT',
        'doviz_path': 'ankara/etimesgut',
        # İstanbul alıcısı da Ankara raporunu alıyor
        'email_envs': ['EMAIL_RECEIVER_ANKARA', 'EMAIL_RECEIVER_ISTANBUL'],
    },
}


class YakitFiyatTakip:
    def __init__(self):
        self.workspace = os.getenv('GITHUB_WORKSPACE', os.getcwd())
        self.veri_dosyasi = os.path.join(self.workspace, 'motorin_fiyatlari.csv')
        self.son_deneme = os.getenv('SON_DENEME', 'false').lower() == 'true'
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

    def verileri_kaydet(self, df):
        df.to_csv(self.veri_dosyasi, index=False)

    @staticmethod
    def alinmis_mi(df, tarih, lokasyon):
        return bool(df.loc[df['tarih'] == tarih, lokasyon].notna().any())

    @staticmethod
    def fiyat_ekle(df, tarih, lokasyon, fiyat):
        df = df.copy()
        if tarih in df['tarih'].values:
            df.loc[df['tarih'] == tarih, lokasyon] = fiyat
        else:
            # Diğer lokasyon sütunları boş (NaN) kalır
            df = pd.concat([df, pd.DataFrame([{'tarih': tarih, lokasyon: fiyat}])], ignore_index=True)[SUTUNLAR]
        return df.sort_values('tarih', ascending=True).reset_index(drop=True)

    # ── Selenium ─────────────────────────────────────────────────────────────

    def setup_driver(self):
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        self.driver = webdriver.Chrome(service=Service(), options=options)
        print("✓ WebDriver başlatıldı")

    def close_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def screenshot_kaydet(self, ad):
        try:
            path = os.path.join(self.workspace, f"hata_screenshot_{ad}.png")
            self.driver.save_screenshot(path)
            print(f"→ Screenshot kaydedildi: {path}")
        except Exception:
            pass

    # ── Kaynaklar ────────────────────────────────────────────────────────────

    def _shell_motorin(self, il, ilce):
        """Tablo seçili il/ilçeyi gösteriyorsa motorin fiyatını, henüz göstermiyorsa None döner."""
        basliklar, satirlar = self.driver.execute_script("""
            const th = [...document.querySelectorAll('table th')].map(e => e.innerText.trim());
            const rows = [...document.querySelectorAll('table tbody tr')]
                .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()));
            return [th, rows];""")
        # Shell zaman zaman iki motorin ürünü listeliyor (ör. Fuelsave Diesel + V-Power Diesel);
        # ürünü olmayan dönemde hücre boş ya da "-" oluyor, ilk sayısal motorin hücresi alınır
        motorin_idx = [i for i, b in enumerate(basliklar) if b.startswith('Motorin')]
        if not motorin_idx or not any(h and h[0] == il for h in satirlar):
            return None
        for hucreler in satirlar:
            if hucreler and hucreler[0] == ilce and len(hucreler) == len(basliklar):
                degerler = [hucreler[i] for i in motorin_idx if re.fullmatch(r'[\d.]+,\d+', hucreler[i])]
                if degerler:
                    return float(degerler[0].replace('.', '').replace(',', '.'))
        return None

    def shell_fiyatlari_cek(self, lokasyon_keys, bugun):
        """
        Shell'in resmi panelinden fiyatları okur. (liste_tarihi, {lokasyon: fiyat}) döner.
        Panelin gösterdiği liste bugünün değilse fiyat okunmaz. Panele ulaşılamazsa exception fırlatır.
        """
        print("→ Shell fiyat paneli açılıyor...")
        self.driver.get(SHELL_URL)
        wait = WebDriverWait(self.driver, 60,
                             ignored_exceptions=(NoSuchElementException, StaleElementReferenceException))
        # "12.09.2026 Tarihinde Geçerli ..." başlığı tablodan sonra yükleniyor, görünene kadar bekle
        eslesme = wait.until(lambda d: re.search(
            r'(\d{2})\.(\d{2})\.(\d{4}) Tarihinde Geçerli', d.find_element(By.TAG_NAME, 'body').text))
        liste_tarihi = f"{eslesme.group(3)}-{eslesme.group(2)}-{eslesme.group(1)}"
        print(f"✓ Shell listesi: {liste_tarihi} tarihinde geçerli")
        if liste_tarihi != bugun:
            return liste_tarihi, {}

        fiyatlar = {}
        for key in lokasyon_keys:
            il, ilce = LOKASYONLAR[key]['shell_il'], LOKASYONLAR[key]['shell_ilce']
            try:
                wait.until(lambda d: Select(d.find_element(By.ID, 'city-select')).select_by_visible_text(il) or True)
                wait.until(lambda d: ilce in d.execute_script(
                    "return [...document.querySelectorAll('#county-select option')].map(o => o.text)"))
                wait.until(lambda d: Select(d.find_element(By.ID, 'county-select')).select_by_visible_text(ilce) or True)
                fiyatlar[key] = wait.until(lambda d: self._shell_motorin(il, ilce))
                print(f"✓ {LOKASYONLAR[key]['adi']}: {fiyatlar[key]:.2f} ₺ (Shell)")
            except Exception as e:
                print(f"✗ Shell'den okunamadı ({LOKASYONLAR[key]['adi']}): {type(e).__name__}: {str(e).strip()[:200]}")
                self.screenshot_kaydet(f"shell_{key}")
        return liste_tarihi, fiyatlar

    def doviz_fiyati_cek(self, lokasyon_key):
        """Yedek kaynak. (fiyat, doviz.com'un veri tarihi) döner."""
        url = DOVIZ_URL.format(LOKASYONLAR[lokasyon_key]['doviz_path'])
        istek = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(istek, timeout=30).read().decode('utf-8')
        hucreler = re.findall(r'<td class="text-bold p-12 text-center">\s*([^<]+?)\s*</td>', html)
        veri_tarihi = re.search(r'<td class="time p-12 text-center">\s*([^<]+?)\s*</td>', html)
        if len(hucreler) < 2:
            raise Exception("doviz.com'da motorin fiyat elementi bulunamadı")
        fiyat = float(hucreler[1].replace('₺', '').replace('.', '').replace(',', '.'))
        return fiyat, (veri_tarihi.group(1) if veri_tarihi else '?')

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

    def rapor_olustur(self, lokasyon_key, guncel_fiyat, df, tr_time, yedek_notu=None):
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

        kaynak = "doviz.com (yedek kaynak)" if yedek_notu else "Shell resmi fiyat paneli"
        uyari = f"""
                <div style="background-color: #fff3cd; border-left: 4px solid #f0ad4e; padding: 12px 15px; border-radius: 4px; margin-bottom: 20px; color: #856404;">
                    ⚠️ {yedek_notu}
                </div>""" if yedek_notu else ""

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
                {uyari}
                <h2 style="color: #333;">Güncel Fiyat</h2>
                <div style="font-size: 48px; font-weight: bold; color: #DD1D21; margin: 20px 0 5px 0;">
                    {guncel_fiyat:.2f} ₺/Lt
                </div>
                <p style="margin: 0; color: #666; font-size: 13px;">Kaynak: {kaynak}</p>
                {ozet_tablo(haftalik, 'haftalık', guncel_fiyat)}
                {ozet_tablo(aylik, 'aylık', guncel_fiyat)}
                <div style="margin-top: 40px; padding: 15px; background-color: #f9f9f9; border-left: 4px solid #DD1D21; border-radius: 4px;">
                    <p style="margin: 0; color: #666; font-size: 13px;">
                        📅 <strong>{toplam_gun}</strong> gündür takip ediliyor<br>
                        🤖 GitHub Actions — Her sabah Shell günün fiyat listesini yayınlayınca (~06:30 TR) güncellenir.
                    </p>
                </div>
            </div>
        </body>
        </html>"""
        return html

    # ── Email ────────────────────────────────────────────────────────────────

    def email_gonder(self, icerik, alici, tr_time, lokasyon_adi, yedek=False):
        email_gonderen = os.getenv('EMAIL_SENDER')
        email_sifre = os.getenv('SMTP_KEY')
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))

        if not all([email_gonderen, email_sifre, alici]):
            raise ValueError("Email bilgileri eksik (EMAIL_SENDER, SMTP_KEY veya alıcı tanımlı değil)")

        msg = MIMEMultipart('alternative')
        msg['Subject'] = (f"{'⚠️' if yedek else '🔔'} Shell Motorin Fiyatı — {lokasyon_adi} — "
                          f"{tr_time.strftime('%d.%m.%Y')}")
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

    # ── Ana Akış ─────────────────────────────────────────────────────────────

    def calistir(self):
        print("\n" + "=" * 42)
        print("  🚗 SHELL YAKIT FİYAT TAKİP")
        print("=" * 42 + "\n")

        tr_time = datetime.now(timezone.utc) + timedelta(hours=3)
        bugun = tr_time.strftime('%Y-%m-%d')
        df = self.verileri_yukle()

        # CSV'de bugünün fiyatı olan lokasyonlar önceki denemede gönderilmiştir
        bekleyenler = [k for k in LOKASYONLAR if not self.alinmis_mi(df, bugun, k)]
        if not bekleyenler:
            print(f"✓ {bugun} fiyatları zaten alınıp gönderilmiş, yapılacak bir şey yok")
            return 0
        print(f"Tarih: {bugun} | Son deneme: {'evet' if self.son_deneme else 'hayır'}")
        print(f"Bekleyen lokasyonlar: {', '.join(LOKASYONLAR[k]['adi'] for k in bekleyenler)}\n")

        # 1) Shell resmi paneli
        fiyatlar = {}
        try:
            self.setup_driver()
            liste_tarihi, fiyatlar = self.shell_fiyatlari_cek(bekleyenler, bugun)
            if liste_tarihi != bugun:
                print(f"⚠ Shell'in bugünkü listesi henüz yayınlanmamış (panelde {liste_tarihi} listesi var)")
        except Exception as e:
            # Selenium mesajları stacktrace içeriyor, ilk satır yeterli
            ilk_satir = str(e).strip().splitlines()[0] if str(e).strip() else ''
            print(f"✗ Shell paneline ulaşılamadı: {type(e).__name__}: {ilk_satir}")
            self.screenshot_kaydet("shell")
        finally:
            self.close_driver()

        # 2) Son denemede Shell'den alınamayanlar için doviz.com
        yedek_notlari = {}
        eksikler = [k for k in bekleyenler if k not in fiyatlar]
        if eksikler and not self.son_deneme:
            print(f"\n→ {len(eksikler)} lokasyon sonraki denemeye bırakıldı")
        elif eksikler:
            print("\n── Son deneme: doviz.com yedek kaynağı ──")
            for k in eksikler:
                try:
                    fiyat, veri_tarihi = self.doviz_fiyati_cek(k)
                    fiyatlar[k] = fiyat
                    yedek_notlari[k] = (
                        "Shell'in resmi fiyat paneline ulaşılamadı veya bugünkü liste yayınlanmadı. "
                        f"Bu fiyat doviz.com'dan alındı (doviz.com veri tarihi: {veri_tarihi}) ve güncel olmayabilir."
                    )
                    print(f"✓ {LOKASYONLAR[k]['adi']}: {fiyat:.2f} ₺ (doviz.com, veri tarihi {veri_tarihi})")
                except Exception as e:
                    print(f"✗ doviz.com'dan da alınamadı ({LOKASYONLAR[k]['adi']}): {e}")

        # 3) Rapor, mail ve kayıt
        hatalar = []
        for k in bekleyenler:
            adi = LOKASYONLAR[k]['adi']
            if k not in fiyatlar:
                if self.son_deneme:
                    hatalar.append(adi)
                continue

            print(f"\n── {adi} ──")
            yeni_df = self.fiyat_ekle(df, bugun, k, fiyatlar[k])
            envs = LOKASYONLAR[k]['email_envs']
            alicilar = [os.getenv(e) for e in envs if os.getenv(e)]
            try:
                if alicilar:
                    rapor = self.rapor_olustur(k, fiyatlar[k], yeni_df, tr_time, yedek_notlari.get(k))
                    for alici in alicilar:
                        self.email_gonder(rapor, alici, tr_time, adi, yedek=k in yedek_notlari)
                elif envs:
                    print(f"⚠ Alıcı tanımlı değil ({', '.join(envs)}), email atlandı")
                else:
                    print("→ Bu lokasyon için mail gönderilmiyor")
                basarili = True
            except Exception as e:
                print(f"✗ Email gönderilemedi: {e}")
                hatalar.append(adi)
                basarili = False

            # Mail gidemezse sonraki deneme tekrar denesin diye kaydetme; son denemede fiyatı yine de kaydet
            if basarili or self.son_deneme:
                df = yeni_df
                self.verileri_kaydet(df)

        print("\n" + "=" * 42)
        if hatalar:
            print(f"  ⚠ Hatalı lokasyonlar: {', '.join(hatalar)}")
            return 1
        print("  ✅ Tamamlandı")
        return 0


if __name__ == "__main__":
    sys.exit(YakitFiyatTakip().calistir())
