# Etikett – webbapp för Phomemo M110

Skapa och skriv ut etiketter på en Phomemo M110 över Bluetooth direkt från webbläsaren.

**Öppna:** https://furiz.github.io/etikett/

## Webbläsare
- **iPhone/iPad:** Safari saknar Web Bluetooth. Använd appen **Bluefy** (App Store) och öppna adressen där.
- **Android, Windows, macOS, ChromeOS:** Chrome eller Edge.

Koppla från skrivaren i Phomemo-appen först – skrivaren kan bara vara ansluten till en enhet åt gången.

## Funktioner
- Mallar (pris, datumetiketter, namnlappar, fest, QR för Wi-Fi m.m.) och egna sparade mallar
- Text med flera typsnitt, bilder (med rastrering), QR-koder, streckkoder, ramar, linjer, dagens datum
- Etikettstorlekar 25×15 till 50×80 mm samt egen storlek
- Svärta, hastighet, papperstyp, antal kopior, utskriftshistorik, export till PNG

## Protokoll (M110)
BLE-tjänst `0xFF00`, skriv till `0xFF02` (notiser på `0xFF03`). Varje jobb:

```
1B 4E 0D <hastighet 1–5>
1B 4E 04 <svärta 1–15>
1F 11 <papper: 0A mellanrum, 0B löpande, 26 svart markering>
1D 76 30 00 <byte/rad LE16> <rader LE16> <raster, 1 bit/punkt, MSB först, 1 = svart>
1F F0 05 00
1F F0 03 00
```
203 dpi (8 punkter/mm), skrivhuvud max 384 punkter. Bibliotek i `lib/`: qrcode-generator (MIT), JsBarcode (MIT).
