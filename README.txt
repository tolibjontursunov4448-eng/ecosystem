ECOSYSTEM - ishga tushirish
1) pip install -r requirements.txt   (yoki start.bat ustiga ikki marta bosing)
2) python app.py  -> brauzer o'zi ochiladi (http://127.0.0.1:5000)
Admin: tolibjon / 2008 (admin panelda almashtiring)
Kalitlar: app.py boshida IMGBB_KEY, JSONBIN_ID, JSONBIN_KEY ni to'ldiring.
QR kodlar saytning manzilini o'zida saqlaydi: haqiqiy domen (https) ochilgandan keyin daraxt qo'shing yoki QR ni qayta yuklab oling.
Kamera/GPS faqat HTTPS yoki localhost da ishlaydi.

QR kodlar: app.py boshidagi PUBLIC_URL ga haqiqiy sayt manzilini yozing (masalan https://ecosystem.uz). Bo'sh bo'lsa va sayt localhost da ochilgan bo'lsa, QR kompyuterning Wi-Fi manzilini (masalan http://192.168.1.5:5000) saqlaydi - telefon shu Wi-Fi da bo'lsa ochiladi.
Gunicorn bilan ishga tushirsangiz: gunicorn app:app --timeout 120 (20 tagacha rasm yuklash uchun).
