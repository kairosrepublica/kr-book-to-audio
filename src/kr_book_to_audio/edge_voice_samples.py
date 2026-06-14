from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterable
import json
import os
import re
import time
from .durable_io import replace_with_retry

SAMPLE_TEXTS = {
    'zh': 'This is a short Chinese voice preview for pronunciation, speed, and tone.',
    'en': 'This is a short voice preview. Please confirm the voice, speed, and tone.',
    'es': 'Esta es una breve muestra de voz. Confirme la voz, la velocidad y el tono.',
    'pt': 'Esta e uma breve amostra de voz. Confirme a voz, a velocidade e o tom.',
    'tr': 'Bu kisa bir ses ornegidir. Lutfen sesi, hizi ve tonu kontrol edin.',
    'fr': 'Ceci est un court extrait vocal. Verifiez la voix, la vitesse et le ton.',
    'de': 'Dies ist eine kurze Sprachprobe. Pruefen Sie Stimme, Tempo und Tonlage.',
    'it': 'Questo e un breve campione vocale. Verifica voce, velocita e tono.',
    'ja': 'This is a short Japanese voice preview for pronunciation, speed, and tone.',
    'ko': 'This is a short Korean voice preview for pronunciation, speed, and tone.',
    'default': 'This is a short voice preview. Please confirm the voice, speed, and tone.',
}


def safe_name(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '-', str(value)).strip('-') or 'voice'


def sample_text(locale: str, voice: str = '') -> str:
    # Native-locale preview only. Never feed English preview text into a non-English voice.
    def language_code(raw: str) -> str:
        value = str(raw or '').strip().replace('_', '-').lower()
        match = re.match(r'^([a-z]{2,3})(?:-|$)', value)
        return match.group(1) if match else ''

    language = language_code(voice) or language_code(locale)
    samples = {
        'af': 'Hallo. Dit is \u2019n Afrikaanse stemvoorskou. Kontroleer die leestempo en die klank van die stem.',
        'am': '\u1230\u120b\u121d\u1362 \u12ed\u1205 \u12e8\u12a0\u121b\u122d\u129b \u12f5\u121d\u1345 \u1245\u12f5\u1218 \u121b\u12f3\u1218\u132b \u1290\u12cd\u1362 \u12e8\u1295\u1263\u1265 \u134d\u1325\u1290\u1275\u1295 \u12a5\u1293 \u12e8\u12f5\u121d\u1345 \u1325\u122b\u1275\u1295 \u12eb\u1228\u130b\u130d\u1321\u1362',
        'ar': '\u0645\u0631\u062d\u0628\u0627\u064b. \u0647\u0630\u0647 \u0645\u0639\u0627\u064a\u0646\u0629 \u0635\u0648\u062a\u064a\u0629 \u0628\u0627\u0644\u0644\u063a\u0629 \u0627\u0644\u0639\u0631\u0628\u064a\u0629. \u064a\u0631\u062c\u0649 \u0627\u0644\u062a\u062d\u0642\u0642 \u0645\u0646 \u0633\u0631\u0639\u0629 \u0627\u0644\u0642\u0631\u0627\u0621\u0629 \u0648\u0646\u0628\u0631\u0629 \u0627\u0644\u0635\u0648\u062a.',
        'az': 'Salam. Bu, Az\u0259rbaycan dilind\u0259 s\u0259s \xf6nizl\u0259m\u0259sidir. Oxuma s\xfcr\u0259tini v\u0259 s\u0259s tonunu yoxlay\u0131n.',
        'bg': '\u0417\u0434\u0440\u0430\u0432\u0435\u0439\u0442\u0435. \u0422\u043e\u0432\u0430 \u0435 \u043f\u0440\u0435\u0434\u0432\u0430\u0440\u0438\u0442\u0435\u043b\u0435\u043d \u043f\u0440\u0435\u0433\u043b\u0435\u0434 \u043d\u0430 \u0431\u044a\u043b\u0433\u0430\u0440\u0441\u043a\u0438 \u0433\u043b\u0430\u0441. \u041f\u0440\u043e\u0432\u0435\u0440\u0435\u0442\u0435 \u0441\u043a\u043e\u0440\u043e\u0441\u0442\u0442\u0430 \u0438 \u0442\u0435\u043c\u0431\u044a\u0440\u0430.',
        'bn': '\u09a8\u09ae\u09b8\u09cd\u0995\u09be\u09b0\u0964 \u098f\u099f\u09bf \u09ac\u09be\u0982\u09b2\u09be \u0995\u09a3\u09cd\u09a0\u09c7\u09b0 \u09a8\u09ae\u09c1\u09a8\u09be\u0964 \u09aa\u09a1\u09bc\u09be\u09b0 \u0997\u09a4\u09bf \u098f\u09ac\u0982 \u0995\u09a3\u09cd\u09a0\u09c7\u09b0 \u09b8\u09cd\u09ac\u09b0 \u09aa\u09b0\u09c0\u0995\u09cd\u09b7\u09be \u0995\u09b0\u09c1\u09a8\u0964',
        'bs': 'Zdravo. Ovo je pregled glasa na bosanskom jeziku. Provjerite brzinu \u010ditanja i ton glasa.',
        'ca': 'Hola. Aquesta \xe9s una previsualitzaci\xf3 de veu en catal\xe0. Comproveu la velocitat i el to de veu.',
        'cs': 'Dobr\xfd den. Toto je uk\xe1zka \u010desk\xe9ho hlasu. Zkontrolujte rychlost \u010dten\xed a barvu hlasu.',
        'cy': 'Helo. Dyma ragolwg llais Cymraeg. Gwiriwch gyflymder y darllen ac ansawdd y llais.',
        'da': 'Hej. Dette er en dansk stemmepr\xf8ve. Kontroll\xe9r l\xe6sehastigheden og stemmens klang.',
        'de': 'Guten Tag. Dies ist eine deutsche Sprachvorschau. Pr\xfcfen Sie Lesegeschwindigkeit und Klangfarbe.',
        'el': '\u0393\u03b5\u03b9\u03b1 \u03c3\u03b1\u03c2. \u0391\u03c5\u03c4\u03ae \u03b5\u03af\u03bd\u03b1\u03b9 \u03bc\u03b9\u03b1 \u03c0\u03c1\u03bf\u03b5\u03c0\u03b9\u03c3\u03ba\u03cc\u03c0\u03b7\u03c3\u03b7 \u03b5\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ae\u03c2 \u03c6\u03c9\u03bd\u03ae\u03c2. \u0395\u03bb\u03ad\u03b3\u03be\u03c4\u03b5 \u03c4\u03b7\u03bd \u03c4\u03b1\u03c7\u03cd\u03c4\u03b7\u03c4\u03b1 \u03ba\u03b1\u03b9 \u03c4\u03bf\u03bd \u03c4\u03cc\u03bd\u03bf.',
        'en': 'Hello. This is an English voice preview. Check the reading speed, pronunciation, and tone before generating the audiobook.',
        'es': 'Hola. Esta es una vista previa de voz en espa\xf1ol. Compruebe la velocidad de lectura y el tono de la voz.',
        'et': 'Tere. See on eestikeelse h\xe4\xe4le eelvaade. Kontrollige lugemiskiirust ja h\xe4\xe4le k\xf5la.',
        'eu': 'Kaixo. Hau euskarazko ahotsaren aurrebista da. Egiaztatu irakurketa-abiadura eta ahotsaren tonua.',
        'fa': '\u0633\u0644\u0627\u0645. \u0627\u06cc\u0646 \u06cc\u06a9 \u067e\u06cc\u0634\u200c\u0646\u0645\u0627\u06cc\u0634 \u0635\u062f\u0627\u06cc \u0641\u0627\u0631\u0633\u06cc \u0627\u0633\u062a. \u0633\u0631\u0639\u062a \u062e\u0648\u0627\u0646\u062f\u0646 \u0648 \u0644\u062d\u0646 \u0635\u062f\u0627 \u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646\u06cc\u062f.',
        'fi': 'Hei. T\xe4m\xe4 on suomenkielisen \xe4\xe4nen esikatselu. Tarkista lukunopeus ja \xe4\xe4nen s\xe4vy.',
        'fil': 'Kumusta. Ito ay paunang pakikinig sa boses na Filipino. Suriin ang bilis at tono ng pagbasa.',
        'fr': 'Bonjour. Ceci est un aper\xe7u vocal en fran\xe7ais. V\xe9rifiez la vitesse de lecture et la qualit\xe9 de la voix.',
        'ga': 'Dia dhuit. Seo r\xe9amhamharc gutha Gaeilge. Seice\xe1il luas na l\xe9itheoireachta agus ton an ghutha.',
        'gl': 'Ola. Esta \xe9 unha vista previa de voz en galego. Comprobe a velocidade e o ton da voz.',
        'gu': '\u0aa8\u0aae\u0ab8\u0acd\u0aa4\u0ac7. \u0a86 \u0a97\u0ac1\u0a9c\u0ab0\u0abe\u0aa4\u0ac0 \u0a85\u0ab5\u0abe\u0a9c\u0aa8\u0ac1\u0a82 \u0aaa\u0ac2\u0ab0\u0acd\u0ab5\u0abe\u0ab5\u0ab2\u0acb\u0a95\u0aa8 \u0a9b\u0ac7. \u0ab5\u0abe\u0a82\u0a9a\u0aa8\u0aa8\u0ac0 \u0a97\u0aa4\u0abf \u0a85\u0aa8\u0ac7 \u0a85\u0ab5\u0abe\u0a9c\u0aa8\u0acb \u0ab8\u0acd\u0ab5\u0ab0 \u0aa4\u0aaa\u0abe\u0ab8\u0acb.',
        'he': '\u05e9\u05dc\u05d5\u05dd. \u05d6\u05d5\u05d4\u05d9 \u05ea\u05e6\u05d5\u05d2\u05d4 \u05de\u05e7\u05d3\u05d9\u05de\u05d4 \u05e9\u05dc \u05e7\u05d5\u05dc \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea. \u05d1\u05d3\u05e7\u05d5 \u05d0\u05ea \u05de\u05d4\u05d9\u05e8\u05d5\u05ea \u05d4\u05e7\u05e8\u05d9\u05d0\u05d4 \u05d5\u05d0\u05ea \u05d2\u05d5\u05d5\u05df \u05d4\u05e7\u05d5\u05dc.',
        'hi': '\u0928\u092e\u0938\u094d\u0924\u0947\u0964 \u092f\u0939 \u0939\u093f\u0902\u0926\u0940 \u0906\u0935\u093e\u091c\u093c \u0915\u093e \u092a\u0942\u0930\u094d\u0935\u093e\u0935\u0932\u094b\u0915\u0928 \u0939\u0948\u0964 \u0915\u0943\u092a\u092f\u093e \u092a\u0922\u093c\u0928\u0947 \u0915\u0940 \u0917\u0924\u093f \u0914\u0930 \u0906\u0935\u093e\u091c\u093c \u0915\u0940 \u0917\u0941\u0923\u0935\u0924\u094d\u0924\u093e \u091c\u093e\u0901\u091a\u0947\u0902\u0964',
        'hr': 'Pozdrav. Ovo je pregled hrvatskog glasa. Provjerite brzinu \u010ditanja i ton glasa.',
        'hu': '\xdcdv\xf6zl\xf6m. Ez egy magyar hangel\u0151n\xe9zet. Ellen\u0151rizze az olvas\xe1si sebess\xe9get \xe9s a hangsz\xednt.',
        'hy': '\u0532\u0561\u0580\u0587\u0589 \u054d\u0561 \u0570\u0561\u0575\u0565\u0580\u0565\u0576 \u0571\u0561\u0575\u0576\u056b \u0576\u0561\u056d\u0561\u0564\u056b\u057f\u0578\u0582\u0574 \u0567\u0589 \u054d\u057f\u0578\u0582\u0563\u0565\u0584 \u0568\u0576\u0569\u0565\u0580\u0581\u0574\u0561\u0576 \u0561\u0580\u0561\u0563\u0578\u0582\u0569\u0575\u0578\u0582\u0576\u0568 \u0587 \u0571\u0561\u0575\u0576\u056b \u057f\u0578\u0576\u0568\u0589',
        'id': 'Halo. Ini adalah pratinjau suara bahasa Indonesia. Periksa kecepatan membaca dan warna suara.',
        'is': 'Hall\xf3. \xdeetta er \xedslensk radds\xfdnishorn. Athuga\xf0u lestrarhra\xf0a og t\xf3n raddarinnar.',
        'it': 'Buongiorno. Questa \xe8 un\u2019anteprima vocale in italiano. Controlli la velocit\xe0 di lettura e il tono della voce.',
        'ja': '\u3053\u3093\u306b\u3061\u306f\u3002\u3053\u308c\u306f\u65e5\u672c\u8a9e\u306e\u97f3\u58f0\u30d7\u30ec\u30d3\u30e5\u30fc\u3067\u3059\u3002\u8aad\u307f\u4e0a\u3052\u306e\u901f\u3055\u3068\u97f3\u8cea\u3092\u78ba\u8a8d\u3057\u3066\u304f\u3060\u3055\u3044\u3002',
        'jv': 'Halo. Iki pratinjau swara basa Jawa. Priksa kacepetan maca lan warna swarane.',
        'ka': '\u10d2\u10d0\u10db\u10d0\u10e0\u10ef\u10dd\u10d1\u10d0. \u10d4\u10e1 \u10d0\u10e0\u10d8\u10e1 \u10e5\u10d0\u10e0\u10d7\u10e3\u10da\u10d8 \u10ee\u10db\u10d8\u10e1 \u10ec\u10d8\u10dc\u10d0\u10e1\u10ec\u10d0\u10e0\u10d8 \u10db\u10dd\u10e1\u10db\u10d4\u10dc\u10d0. \u10e8\u10d4\u10d0\u10db\u10dd\u10ec\u10db\u10d4\u10d7 \u10d9\u10d8\u10d7\u10ee\u10d5\u10d8\u10e1 \u10e1\u10d8\u10e9\u10e5\u10d0\u10e0\u10d4 \u10d3\u10d0 \u10e2\u10dd\u10dc\u10d8.',
        'kk': '\u0421\u04d9\u043b\u0435\u043c\u0435\u0442\u0441\u0456\u0437 \u0431\u0435. \u0411\u04b1\u043b \u049b\u0430\u0437\u0430\u049b \u0442\u0456\u043b\u0456\u043d\u0434\u0435\u0433\u0456 \u0434\u0430\u0443\u044b\u0441 \u04af\u043b\u0433\u0456\u0441\u0456. \u041e\u049b\u0443 \u0436\u044b\u043b\u0434\u0430\u043c\u0434\u044b\u0493\u044b \u043c\u0435\u043d \u0434\u0430\u0443\u044b\u0441 \u0440\u0435\u04a3\u043a\u0456\u043d \u0442\u0435\u043a\u0441\u0435\u0440\u0456\u04a3\u0456\u0437.',
        'km': '\u179f\u17bd\u179f\u17d2\u178f\u17b8\u17d4 \u1793\u17c1\u17c7\u1787\u17b6\u1780\u17b6\u179a\u179f\u17d2\u178f\u17b6\u1794\u17cb\u179f\u17b6\u1780\u179b\u17d2\u1794\u1784\u179f\u17c6\u17a1\u17c1\u1784\u1797\u17b6\u179f\u17b6\u1781\u17d2\u1798\u17c2\u179a\u17d4 \u179f\u17bc\u1798\u1796\u17b7\u1793\u17b7\u178f\u17d2\u1799\u179b\u17d2\u1794\u17bf\u1793\u17a2\u17b6\u1793 \u1793\u17b7\u1784\u179f\u17c6\u1793\u17c0\u1784\u17d4',
        'kn': '\u0ca8\u0cae\u0cb8\u0ccd\u0c95\u0cbe\u0cb0. \u0c87\u0ca6\u0cc1 \u0c95\u0ca8\u0ccd\u0ca8\u0ca1 \u0ca7\u0ccd\u0cb5\u0ca8\u0cbf\u0caf \u0caa\u0cc2\u0cb0\u0ccd\u0cb5\u0cb5\u0cc0\u0c95\u0ccd\u0cb7\u0ca3\u0cc6. \u0c93\u0ca6\u0cc1\u0cb5 \u0cb5\u0cc7\u0c97 \u0cae\u0ca4\u0ccd\u0ca4\u0cc1 \u0ca7\u0ccd\u0cb5\u0ca8\u0cbf\u0caf \u0cb8\u0ccd\u0cb5\u0cb0\u0cb5\u0ca8\u0ccd\u0ca8\u0cc1 \u0caa\u0cb0\u0cbf\u0cb6\u0cc0\u0cb2\u0cbf\u0cb8\u0cbf.',
        'ko': '\uc548\ub155\ud558\uc138\uc694. \uc774\uac83\uc740 \ud55c\uad6d\uc5b4 \uc74c\uc131 \ubbf8\ub9ac\ub4e3\uae30\uc785\ub2c8\ub2e4. \uc77d\uae30 \uc18d\ub3c4\uc640 \uc74c\uc0c9\uc744 \ud655\uc778\ud558\uc138\uc694.',
        'lo': '\u0eaa\u0eb0\u0e9a\u0eb2\u0e8d\u0e94\u0eb5. \u0e99\u0eb5\u0ec9\u0ec1\u0ea1\u0ec8\u0e99\u0e95\u0ebb\u0ea7\u0ea2\u0ec8\u0eb2\u0e87\u0eaa\u0ebd\u0e87\u0e9e\u0eb2\u0eaa\u0eb2\u0ea5\u0eb2\u0ea7. \u0e81\u0eb0\u0ea5\u0eb8\u0e99\u0eb2\u0e81\u0ea7\u0e94\u0eaa\u0ead\u0e9a\u0e84\u0ea7\u0eb2\u0ea1\u0ec4\u0ea7 \u0ec1\u0ea5\u0eb0 \u0e99\u0ec9\u0eb3\u0eaa\u0ebd\u0e87.',
        'lt': 'Sveiki. Tai lietuvi\u0161ko balso per\u017ei\u016bra. Patikrinkite skaitymo greit\u012f ir balso tembr\u0105.',
        'lv': 'Labdien. \u0160is ir latvie\u0161u balss priek\u0161skat\u012bjums. P\u0101rbaudiet las\u012b\u0161anas \u0101trumu un balss toni.',
        'mk': '\u0417\u0434\u0440\u0430\u0432\u043e. \u041e\u0432\u0430 \u0435 \u043f\u0440\u0435\u0433\u043b\u0435\u0434 \u043d\u0430 \u043c\u0430\u043a\u0435\u0434\u043e\u043d\u0441\u043a\u0438 \u0433\u043b\u0430\u0441. \u041f\u0440\u043e\u0432\u0435\u0440\u0435\u0442\u0435 \u0458\u0430 \u0431\u0440\u0437\u0438\u043d\u0430\u0442\u0430 \u043d\u0430 \u0447\u0438\u0442\u0430\u045a\u0435 \u0438 \u0442\u043e\u043d\u043e\u0442.',
        'ml': '\u0d28\u0d2e\u0d38\u0d4d\u0d15\u0d3e\u0d30\u0d02. \u0d07\u0d24\u0d4d \u0d2e\u0d32\u0d2f\u0d3e\u0d33\u0d02 \u0d36\u0d2c\u0d4d\u0d26\u0d24\u0d4d\u0d24\u0d3f\u0d28\u0d4d\u0d31\u0d46 \u0d2e\u0d41\u0d7b\u0d15\u0d42\u0d7c \u0d15\u0d47\u0d7e\u0d35\u0d3f\u0d2f\u0d3e\u0d23\u0d4d. \u0d35\u0d3e\u0d2f\u0d28\u0d2f\u0d41\u0d1f\u0d46 \u0d35\u0d47\u0d17\u0d35\u0d41\u0d02 \u0d36\u0d2c\u0d4d\u0d26\u0d2d\u0d3e\u0d35\u0d35\u0d41\u0d02 \u0d2a\u0d30\u0d3f\u0d36\u0d4b\u0d27\u0d3f\u0d15\u0d4d\u0d15\u0d41\u0d15.',
        'mn': '\u0421\u0430\u0439\u043d \u0431\u0430\u0439\u043d\u0430 \u0443\u0443. \u042d\u043d\u044d \u0431\u043e\u043b \u043c\u043e\u043d\u0433\u043e\u043b \u0434\u0443\u0443 \u0445\u043e\u043e\u043b\u043e\u0439\u043d \u0443\u0440\u044c\u0434\u0447\u0438\u043b\u0441\u0430\u043d \u0441\u043e\u043d\u0441\u0433\u043e\u043b. \u0423\u043d\u0448\u0438\u0445 \u0445\u0443\u0440\u0434 \u0431\u043e\u043b\u043e\u043d \u04e9\u043d\u0433\u0438\u0439\u0433 \u0448\u0430\u043b\u0433\u0430\u043d\u0430 \u0443\u0443.',
        'mr': '\u0928\u092e\u0938\u094d\u0915\u093e\u0930. \u0939\u0947 \u092e\u0930\u093e\u0920\u0940 \u0906\u0935\u093e\u091c\u093e\u091a\u0947 \u092a\u0942\u0930\u094d\u0935\u093e\u0935\u0932\u094b\u0915\u0928 \u0906\u0939\u0947. \u0935\u093e\u091a\u0928\u093e\u091a\u093e \u0935\u0947\u0917 \u0906\u0923\u093f \u0906\u0935\u093e\u091c\u093e\u091a\u093e \u0938\u0942\u0930 \u0924\u092a\u093e\u0938\u093e.',
        'ms': 'Helo. Ini ialah pratonton suara bahasa Melayu. Semak kelajuan bacaan dan nada suara.',
        'mt': 'Bon\u0121u. Din hija previ\u017cjoni tal-vu\u010bi bil-Malti. I\u010b\u010bekkja l-velo\u010bit\xe0 tal-qari u t-ton tal-vu\u010bi.',
        'my': '\u1019\u1004\u103a\u1039\u1002\u101c\u102c\u1015\u102b\u104b \u1024\u101e\u100a\u103a\u1019\u103e\u102c \u1019\u103c\u1014\u103a\u1019\u102c\u1021\u101e\u1036 \u1014\u1019\u1030\u1014\u102c\u1016\u103c\u1005\u103a\u101e\u100a\u103a\u104b \u1016\u1010\u103a\u1014\u103e\u102f\u1014\u103a\u1038\u1014\u103e\u1004\u1037\u103a \u1021\u101e\u1036\u1021\u101b\u1031\u102c\u1004\u103a\u1000\u102d\u102f \u1005\u1005\u103a\u1006\u1031\u1038\u1015\u102b\u104b',
        'nb': 'Hei. Dette er en norsk stemmepr\xf8ve. Kontroller lesehastigheten og klangen i stemmen.',
        'ne': '\u0928\u092e\u0938\u094d\u0915\u093e\u0930\u0964 \u092f\u094b \u0928\u0947\u092a\u093e\u0932\u0940 \u0906\u0935\u093e\u091c\u0915\u094b \u092a\u0942\u0930\u094d\u0935\u093e\u0935\u0932\u094b\u0915\u0928 \u0939\u094b\u0964 \u092a\u0922\u094d\u0928\u0947 \u0917\u0924\u093f \u0930 \u0906\u0935\u093e\u091c\u0915\u094b \u0938\u094d\u0935\u0930 \u091c\u093e\u0901\u091a \u0917\u0930\u094d\u0928\u0941\u0939\u094b\u0938\u094d\u0964',
        'nl': 'Hallo. Dit is een Nederlandse stemvoorbeeld. Controleer de leessnelheid en de klank van de stem.',
        'pa': '\u0a38\u0a24 \u0a38\u0a4d\u0a30\u0a40 \u0a05\u0a15\u0a3e\u0a32\u0964 \u0a07\u0a39 \u0a2a\u0a70\u0a1c\u0a3e\u0a2c\u0a40 \u0a06\u0a35\u0a3e\u0a1c\u0a3c \u0a26\u0a40 \u0a1d\u0a32\u0a15 \u0a39\u0a48\u0964 \u0a2a\u0a5c\u0a4d\u0a39\u0a28 \u0a26\u0a40 \u0a17\u0a24\u0a40 \u0a05\u0a24\u0a47 \u0a06\u0a35\u0a3e\u0a1c\u0a3c \u0a26\u0a3e \u0a32\u0a39\u0a3f\u0a1c\u0a3c\u0a3e \u0a1c\u0a3e\u0a02\u0a1a\u0a4b\u0964',
        'pl': 'Dzie\u0144 dobry. To jest polska pr\xf3bka g\u0142osu. Sprawd\u017a tempo czytania i barw\u0119 g\u0142osu.',
        'ps': '\u0633\u0644\u0627\u0645. \u062f\u0627 \u062f \u067e\u069a\u062a\u0648 \u063a\u0696 \u0645\u062e\u06a9\u062a\u0646\u0647 \u062f\u0647. \u062f \u0644\u0648\u0633\u062a\u0644\u0648 \u0633\u0631\u0639\u062a \u0627\u0648 \u062f \u063a\u0696 \u06a9\u06cc\u0641\u06cc\u062a \u0648\u06ab\u0648\u0631\u0626.',
        'pt': 'Ol\xe1. Esta \xe9 uma pr\xe9via de voz em portugu\xeas. Verifique a velocidade de leitura e o tom da voz.',
        'ro': 'Bun\u0103 ziua. Aceasta este o previzualizare a vocii \xeen limba rom\xe2n\u0103. Verifica\u021bi viteza \u0219i timbrul.',
        'ru': '\u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439\u0442\u0435. \u042d\u0442\u043e \u043f\u0440\u0435\u0434\u0432\u0430\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0435 \u043f\u0440\u043e\u0441\u043b\u0443\u0448\u0438\u0432\u0430\u043d\u0438\u0435 \u0440\u0443\u0441\u0441\u043a\u043e\u0433\u043e \u0433\u043e\u043b\u043e\u0441\u0430. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0441\u043a\u043e\u0440\u043e\u0441\u0442\u044c \u0438 \u0442\u0435\u043c\u0431\u0440.',
        'si': '\u0d86\u0dba\u0dd4\u0db6\u0ddd\u0dc0\u0db1\u0dca. \u0db8\u0dd9\u0dba \u0dc3\u0dd2\u0d82\u0dc4\u0dbd \u0dc4\u0dac \u0db4\u0dd9\u0dbb\u0daf\u0dc3\u0dd4\u0db1\u0d9a\u0dd2. \u0d9a\u0dd2\u0dba\u0dc0\u0dd3\u0db8\u0dda \u0dc0\u0dda\u0d9c\u0dba \u0dc3\u0dc4 \u0dc4\u0dac \u0dc3\u0dca\u0dc0\u0dbb\u0dba \u0db4\u0dbb\u0dd3\u0d9a\u0dca\u0dc2\u0dcf \u0d9a\u0dbb\u0db1\u0dca\u0db1.',
        'sk': 'Dobr\xfd de\u0148. Toto je uk\xe1\u017eka slovensk\xe9ho hlasu. Skontrolujte r\xfdchlos\u0165 \u010d\xedtania a farbu hlasu.',
        'sl': 'Pozdravljeni. To je predogled slovenskega glasu. Preverite hitrost branja in barvo glasu.',
        'so': 'Salaan. Tani waa horudhac cod Soomaali ah. Hubi xawaaraha akhriska iyo codka.',
        'sq': 'P\xebrsh\xebndetje. Kjo \xebsht\xeb nj\xeb prov\xeb e z\xebrit n\xeb shqip. Kontrolloni shpejt\xebsin\xeb dhe tonin.',
        'sr': '\u0417\u0434\u0440\u0430\u0432\u043e. \u041e\u0432\u043e \u0458\u0435 \u043f\u0440\u0435\u0433\u043b\u0435\u0434 \u0441\u0440\u043f\u0441\u043a\u043e\u0433 \u0433\u043b\u0430\u0441\u0430. \u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u0435 \u0431\u0440\u0437\u0438\u043d\u0443 \u0447\u0438\u0442\u0430\u045a\u0430 \u0438 \u0431\u043e\u0458\u0443 \u0433\u043b\u0430\u0441\u0430.',
        'su': 'Halo. Ieu conto sora basa Sunda. Pariksa laju maca jeung warna sora.',
        'sv': 'Hej. Det h\xe4r \xe4r en svensk r\xf6stf\xf6rhandsvisning. Kontrollera l\xe4shastigheten och r\xf6stens klang.',
        'sw': 'Habari. Huu ni mfano wa sauti ya Kiswahili. Angalia kasi ya kusoma na toni ya sauti.',
        'ta': '\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd. \u0b87\u0ba4\u0bc1 \u0ba4\u0bae\u0bbf\u0bb4\u0bcd \u0b95\u0bc1\u0bb0\u0bb2\u0bcd \u0bae\u0bc1\u0ba9\u0bcd\u0ba9\u0bcb\u0b9f\u0bcd\u0b9f\u0bae\u0bcd. \u0bb5\u0bbe\u0b9a\u0bbf\u0baa\u0bcd\u0baa\u0bc1 \u0bb5\u0bc7\u0b95\u0bae\u0bcd \u0bae\u0bb1\u0bcd\u0bb1\u0bc1\u0bae\u0bcd \u0b95\u0bc1\u0bb0\u0bb2\u0bbf\u0ba9\u0bcd \u0ba4\u0bca\u0ba9\u0bbf\u0baf\u0bc8\u0b9a\u0bcd \u0b9a\u0bb0\u0bbf\u0baa\u0bbe\u0bb0\u0bcd\u0b95\u0bcd\u0b95\u0bb5\u0bc1\u0bae\u0bcd.',
        'te': '\u0c28\u0c2e\u0c38\u0c4d\u0c15\u0c3e\u0c30\u0c02. \u0c07\u0c26\u0c3f \u0c24\u0c46\u0c32\u0c41\u0c17\u0c41 \u0c38\u0c4d\u0c35\u0c30\u0c2a\u0c41 \u0c2e\u0c41\u0c02\u0c26\u0c38\u0c4d\u0c24\u0c41 \u0c35\u0c3f\u0c28\u0c3f\u0c15\u0c3f\u0c21\u0c3f. \u0c1a\u0c26\u0c3f\u0c35\u0c47 \u0c35\u0c47\u0c17\u0c02 \u0c2e\u0c30\u0c3f\u0c2f\u0c41 \u0c38\u0c4d\u0c35\u0c30\u0c3e\u0c28\u0c4d\u0c28\u0c3f \u0c2a\u0c30\u0c3f\u0c36\u0c40\u0c32\u0c3f\u0c02\u0c1a\u0c02\u0c21\u0c3f.',
        'th': '\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35 \u0e19\u0e35\u0e48\u0e04\u0e37\u0e2d\u0e15\u0e31\u0e27\u0e2d\u0e22\u0e48\u0e32\u0e07\u0e40\u0e2a\u0e35\u0e22\u0e07\u0e20\u0e32\u0e29\u0e32\u0e44\u0e17\u0e22 \u0e42\u0e1b\u0e23\u0e14\u0e15\u0e23\u0e27\u0e08\u0e2a\u0e2d\u0e1a\u0e04\u0e27\u0e32\u0e21\u0e40\u0e23\u0e47\u0e27\u0e41\u0e25\u0e30\u0e19\u0e49\u0e33\u0e40\u0e2a\u0e35\u0e22\u0e07',
        'tr': 'Merhaba. Bu, T\xfcrk\xe7e ses \xf6nizlemesidir. Okuma h\u0131z\u0131n\u0131 ve ses tonunu kontrol edin.',
        'uk': '\u0412\u0456\u0442\u0430\u044e. \u0426\u0435 \u043f\u043e\u043f\u0435\u0440\u0435\u0434\u043d\u0454 \u043f\u0440\u043e\u0441\u043b\u0443\u0445\u043e\u0432\u0443\u0432\u0430\u043d\u043d\u044f \u0443\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u043e\u0433\u043e \u0433\u043e\u043b\u043e\u0441\u0443. \u041f\u0435\u0440\u0435\u0432\u0456\u0440\u0442\u0435 \u0448\u0432\u0438\u0434\u043a\u0456\u0441\u0442\u044c \u0456 \u0442\u0435\u043c\u0431\u0440.',
        'ur': '\u0627\u0644\u0633\u0644\u0627\u0645 \u0639\u0644\u06cc\u06a9\u0645\u06d4 \u06cc\u06c1 \u0627\u0631\u062f\u0648 \u0622\u0648\u0627\u0632 \u06a9\u0627 \u067e\u06cc\u0634 \u0645\u0646\u0638\u0631 \u06c1\u06d2\u06d4 \u067e\u0691\u06be\u0646\u06d2 \u06a9\u06cc \u0631\u0641\u062a\u0627\u0631 \u0627\u0648\u0631 \u0622\u0648\u0627\u0632 \u06a9\u06d2 \u0644\u06c1\u062c\u06d2 \u06a9\u0648 \u062c\u0627\u0646\u0686\u06cc\u06ba\u06d4',
        'uz': 'Salom. Bu o\u2018zbekcha ovoz namunasi. O\u2018qish tezligi va ovoz ohangini tekshiring.',
        'vi': 'Xin ch\xe0o. \u0110\xe2y l\xe0 b\u1ea3n xem tr\u01b0\u1edbc gi\u1ecdng n\xf3i ti\u1ebfng Vi\u1ec7t. H\xe3y ki\u1ec3m tra t\u1ed1c \u0111\u1ed9 \u0111\u1ecdc v\xe0 ch\u1ea5t gi\u1ecdng.',
        'cmn': '\u4f60\u597d\uff0c\u6b22\u8fce\u4f7f\u7528\u6709\u58f0\u4e66\u5de5\u4f5c\u53f0\u3002\u8fd9\u662f\u4e00\u6bb5\u666e\u901a\u8bdd\u8bed\u97f3\u8bd5\u542c\uff0c\u8bf7\u68c0\u67e5\u8bed\u901f\u3001\u53d1\u97f3\u548c\u97f3\u8272\u3002',
        'yue': '\u4f60\u597d\uff0c\u6b61\u8fce\u4f7f\u7528\u6709\u8072\u66f8\u5de5\u4f5c\u53f0\u3002\u5462\u6bb5\u4fc2\u7cb5\u8a9e\u8a9e\u97f3\u8a66\u807d\uff0c\u8acb\u6aa2\u67e5\u8a9e\u901f\u3001\u767c\u97f3\u540c\u97f3\u8272\u3002',
        'wuu': '\u4fac\u597d\uff0c\u6b22\u8fce\u4f7f\u7528\u6709\u58f0\u4e66\u5de5\u4f5c\u53f0\u3002\u641e\u662f\u4e00\u6bb5\u5434\u8bed\u8bed\u97f3\u8bd5\u542c\uff0c\u8bf7\u68c0\u67e5\u8bed\u901f\u3001\u53d1\u97f3\u642d\u4ed4\u97f3\u8272\u3002',
        'nan': 'L\xed h\xf3. Tse s\u012b T\xe2i-g\xed sia\u207f-im chh\xec-thia\u207f. Chhi\xe1\u207f ki\xe1m-cha g\xed-sok, hoat-im kap sia\u207f-sek.',
        'zh': '\u4f60\u597d\uff0c\u6b22\u8fce\u4f7f\u7528\u6709\u58f0\u4e66\u5de5\u4f5c\u53f0\u3002\u8fd9\u662f\u4e00\u6bb5\u4e2d\u6587\u8bed\u97f3\u8bd5\u542c\uff0c\u8bf7\u68c0\u67e5\u8bed\u901f\u3001\u53d1\u97f3\u548c\u97f3\u8272\u3002',
        'zu': 'Sawubona. Lesi isibonelo sezwi lesiZulu. Hlola isivinini sokufunda kanye nephimbo lezwi.',
    }
    if language not in samples:
        raise RuntimeError(f'No native-language local preview text is registered for locale={locale!r}, voice={voice!r}. English fallback is prohibited.')
    return samples[language]

@dataclass
class EdgeSampleCache:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def manifest_path(self) -> Path:
        return self.root / 'manifest.json'

    def load(self) -> dict:
        if not self.manifest_path.is_file():
            return {'schema': 1, 'voices': {}}
        try:
            payload = json.loads(self.manifest_path.read_text(encoding='utf-8'))
            return payload if isinstance(payload, dict) else {'schema': 1, 'voices': {}}
        except Exception:
            return {'schema': 1, 'voices': {}}

    def save(self, payload: dict) -> None:
        temp = self.manifest_path.with_name('manifest.json.tmp')
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        replace_with_retry(temp, self.manifest_path)

    def cached_path(self, voice: str) -> Path | None:
        record = self.load().get('voices', {}).get(str(voice), {})
        path = self.root / str(record.get('file') or '')
        return path if path.is_file() and path.stat().st_size > 0 else None

    def generate(self, provider, *, voice: str, locale: str, rate: str = '+0%', pitch: str = '+0Hz', volume: str = '+0%', progress: Callable[[dict], None] | None = None, no_audio_timeout_seconds: float | None = None, total_timeout_seconds: float | None = None) -> Path:
        existing = self.cached_path(voice)
        if existing is not None:
            return existing
        stamp = str(time.time_ns())
        target = self.root / f'{safe_name(voice)}-{stamp}.mp3'
        partial = target.with_suffix('.partial.mp3')
        provider.synthesize(sample_text(locale, voice), partial, voice=voice, rate=rate, pitch=pitch, volume=volume, progress=progress, no_audio_timeout_seconds=float(no_audio_timeout_seconds or os.environ.get('KR_B2A_EDGE_SAMPLE_NO_AUDIO_TIMEOUT_SECONDS', '20')), total_timeout_seconds=float(total_timeout_seconds or os.environ.get('KR_B2A_EDGE_SAMPLE_TOTAL_TIMEOUT_SECONDS', '60')))
        if not partial.is_file() or partial.stat().st_size <= 0:
            raise RuntimeError(f'Edge voice sample was not generated: {voice}')
        replace_with_retry(partial, target)
        manifest = self.load()
        voices = manifest.setdefault('voices', {})
        voices[str(voice)] = {
            'voice': str(voice), 'locale': str(locale), 'file': target.name,
            'generated_at_ns': int(stamp), 'sha256': sha256(target.read_bytes()).hexdigest(),
            'size_bytes': target.stat().st_size, 'status': 'PASS',
        }
        self.save(manifest)
        return target

    def refresh_all(self, provider, voices: Iterable[dict[str, str]], *, progress: Callable[[dict], None] | None = None) -> dict:
        completed = 0
        failed = []
        records = list(voices)
        total = len(records)
        for index, record in enumerate(records, start=1):
            voice = str(record.get('short_name') or '')
            locale = str(record.get('locale') or '')
            if not voice:
                continue
            try:
                path = self.generate(provider, voice=voice, locale=locale, progress=progress)
                completed += 1
                if progress:
                    progress({'event': 'edge-sample-cache', 'state': 'completed', 'voice': voice, 'completed': completed, 'total': total, 'path': str(path)})
            except Exception as exc:
                failed.append({'voice': voice, 'error': f'{type(exc).__name__}: {exc}'})
                if progress:
                    progress({'event': 'edge-sample-cache', 'state': 'failed', 'voice': voice, 'completed': completed, 'total': total, 'error': str(exc)})
        return {'completed': completed, 'failed': failed, 'total': total}
