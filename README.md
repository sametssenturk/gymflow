# GymFlow

GymFlow; spor salonları için geliştirilmiş, Django tabanlı bir yönetim panelidir. Üye kayıtları, üyelik paketleri, ödeme takibi ve operasyon raporları tek bir yönetici arayüzünde toplanır.

Bu proje statik bir arayüz denemesi değil; gerçek iş kurallarını modelleyen, doğrulama ve veri bütünlüğüne odaklanan bir CRM uygulamasıdır. Üyeliklerde paket fiyatı geçmişe dönük korunur, ödemeler kalan borca göre doğrulanır, iptal edilen tahsilatlar denetlenebilir şekilde saklanır ve dashboard verileri ilişkisel kayıtlardan üretilir.

## Özellikler

- Üye listeleme, arama, oluşturma, düzenleme ve silme akışları
- E-posta ve telefon için benzersizlik doğrulamaları
- Üye detay ekranında aktif üyelik, geçmiş üyelikler, ödemeler ve borç durumu
- Paket yönetimi: süre, fiyat, açıklama ve aktif/pasif durumu
- Üyelik yaşam döngüsü: planlandı, aktif, süresi doldu ve donduruldu durumları
- Üyelik dondurma akışı ve bitiş tarihinin otomatik güncellenmesi
- Ödeme kaydı oluşturma, fazla ödeme engeli, ödeme iptali ve iptal geçmişi
- Dashboard KPI'ları: toplam üye, aktif üyelik, yaklaşan bitişler, günlük/aylık tahsilat ve açık bakiye
- Detaylı istatistik sayfası, gelir trendleri, paket dağılımı, ödeme yöntemi kırılımı ve CSV dışa aktarımı
- Giriş yapmadan incelenebilen salt okunur demo dashboard
- Ortam değişkenleriyle yapılandırılabilen deploy ayarları

## Teknolojiler

- Python 3.12
- Django 5.2
- SQLite (yerel geliştirme varsayılanı)
- PostgreSQL desteği (`DATABASE_URL` ile)
- WhiteNoise
- Gunicorn
- Pillow

## Proje Yapısı

```text
accounts/      Kimlik doğrulama, yönetici erişimi ve özel kullanıcı modeli
core/          Genel ana sayfa ve ortak form yardımcıları
dashboard/     KPI dashboard, raporlar, CSV çıktısı ve demo veri üretimi
members/       Üye CRUD, üye detay ekranı ve üyeye bağlı üyelik işlemleri
memberships/   Paket ve üyelik modelleri, formları ve ekranları
payments/      Tahsilat oluşturma, doğrulama, güncelleme ve iptal akışları
templates/     Django template dosyaları
static/        Uygulama stil dosyaları
config/        Django ayarları, URL yönlendirmeleri, ASGI/WSGI girişleri
```

## Veri Modeli

Uygulama dört temel operasyonel model üzerine kuruludur:

- `Member`: üye profili, iletişim bilgileri, fotoğraf, notlar ve hesap özeti
- `MembershipPlan`: üyelik paket kataloğu
- `Membership`: üye ile paket arasındaki ilişki, tarih aralığı, durum ve fiyat geçmişi
- `Payment`: üyeye ve üyeliğe bağlı tahsilat kaydı

`Membership.agreed_price` alanı, paket fiyatı daha sonra değişse bile geçmiş üyeliklerin kendi dönemindeki fiyatla kalmasını sağlar.

## Yerel Kurulum

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Yerel adresler:

- Ana sayfa: `http://127.0.0.1:8000/`
- Demo dashboard: `http://127.0.0.1:8000/demo-dashboard/`
- Yönetici girişi: `http://127.0.0.1:8000/accounts/login/`

## Demo Veri Seti

Demo veri üretimi, 2024'ten beri kullanılan bir spor salonu senaryosunu temsil edecek şekilde tasarlanmıştır. Paket kataloğu korunabilir; üye, üyelik ve ödeme kayıtları yeniden üretilebilir.

Ödeme verileri gerçekçi kalacak şekilde oluşturulur:

- Aylık, 3 aylık ve 6 aylık paketler tek tahsilatla kapatılır.
- Yıllık paketlerde 1, 2 veya 3 taksitli tahsilat senaryoları üretilebilir.
- Tutarlar küsüratsız ve tam lira değerleridir.
- İptal edilen ödemeler ayrı kayıt durumu ile saklanır.

```powershell
python manage.py prepare_portfolio_demo `
  --username demo-admin `
  --password "<güçlü-bir-parola>" `
  --email demo@gymflow.local `
  --members 160 `
  --reset-all-data `
  --preserve-plans
```

Varsayılan `160` üye hedefi, üyelik ve ödeme geçmişiyle birlikte yaklaşık bin operasyon kaydı üretir.

## Veritabanı Davranışı

Yerel geliştirmede `DATABASE_URL` verilmezse uygulama otomatik olarak `db.sqlite3` kullanır. Bu dosya geliştirme ortamına aittir ve `.gitignore` içindedir; GitHub'a yüklenmez.

Deploy ortamında kalıcı veri için PostgreSQL önerilir. `DATABASE_URL` ortam değişkeni tanımlandığında Django PostgreSQL bağlantısını kullanır. Bu sayede aynı kod tabanı yerelde SQLite, canlı ortamda PostgreSQL ile çalışabilir.

## Kimlik Bilgileri

Gerçek parola veya gizli anahtar kaynak koduna yazılmaz. `.env.example` yalnızca örnek değerler içerir.

Demo yönetici hesabı deploy veya yerel kurulum sırasında `prepare_portfolio_demo` komutu ile oluşturulur. Canlı demo bilgileri yayınlandıktan sonra README'ye ayrıca eklenebilir; bu hesap yalnızca portföy demosu için ayrılmış olmalıdır.

## Kalite Kontrolleri

```powershell
python manage.py check
python manage.py test
```

Production benzeri kontrol:

```powershell
$env:DEBUG='0'
$env:SECRET_KEY='uzun-rastgele-bir-secret-key'
$env:ALLOW_SQLITE_IN_PRODUCTION='1'
$env:ALLOWED_HOSTS='127.0.0.1,localhost'
python manage.py check --deploy
```

`ALLOW_SQLITE_IN_PRODUCTION=1` sadece bilinçli demo ortamları için kullanılmalıdır. Kalıcı yayın ortamında PostgreSQL tercih edilmelidir.

## Deploy Notları

Build komutları:

```powershell
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py prepare_portfolio_demo --reset-all-data --preserve-plans
```

Start komutu:

```powershell
gunicorn config.wsgi --bind 0.0.0.0:$PORT --log-file -
```

`Procfile` aynı start komutunu içerir.

Temel ortam değişkenleri:

| Değişken | Açıklama |
| --- | --- |
| `SECRET_KEY` | Django imzalama anahtarı |
| `DEBUG` | Canlı ortamda `0` olmalıdır |
| `ALLOWED_HOSTS` | Virgülle ayrılmış izinli host listesi |
| `CSRF_TRUSTED_ORIGINS` | Deploy edilen HTTPS origin değerleri |
| `DATABASE_URL` | PostgreSQL veya SQLite bağlantı adresi |
| `DB_SSLMODE` | PostgreSQL SSL modu |
| `USE_X_FORWARDED_PROTO` | HTTPS proxy arkasında etkinleştirilir |
| `USE_X_FORWARDED_HOST` | Platform orijinal host bilgisini iletiyorsa etkinleştirilir |
| `PORTFOLIO_DEMO_USERNAME` | Demo yönetici kullanıcı adı |
| `PORTFOLIO_DEMO_PASSWORD` | Demo yönetici parolası |
| `PORTFOLIO_DEMO_MEMBER_COUNT` | Üretilecek demo üye sayısı |
| `PORTFOLIO_DEMO_PRESERVE_PLANS` | Veri yenilenirken paket kataloğunu korur |

## GitHub'a Dahil Edilmeyen Dosyalar

Aşağıdaki dosyalar yerel çalışma çıktısıdır ve repoya eklenmemelidir:

- `.env`
- `db.sqlite3`
- `media/`
- `staticfiles/`
- `*.log`
- `__pycache__/`
- `.venv/` veya `venv/`
