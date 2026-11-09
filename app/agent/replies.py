from __future__ import annotations

from dataclasses import dataclass

from app.llm.language import DEFAULT_LANGUAGE, normalize_language


@dataclass(frozen=True)
class ReplyTemplates:
    clarification: str
    unresolved: str
    available: str
    nearest: str
    confirming: str
    booking_failed: str
    booked: str
    rejected: str
    transfer: str
    concluded: str
    closed_day: str
    all_taken: str
    no_open_day: str
    hangup: str
    thanks: str
    ask_name: str = "ദയവായി പേര് വ്യക്തമാക്കാമോ?"
    cancelled: str = "അപ്പോയിന്റ്മെന്റ് വിജയകരമായി റദ്ദാക്കി (റഫറൻസ് {reference}). നന്ദി!"
    cancel_not_found: str = "ക്ഷമിക്കണം, ഈ റഫറൻസിൽ അപ്പോയിന്റ്മെന്റ് കണ്ടെത്താൻ കഴിഞ്ഞില്ല."
    ask_cancel_ref: str = "അപ്പോയിന്റ്മെന്റ് റദ്ദാക്കാൻ ദയവായി ബുക്കിംഗ് റഫറൻസ് നമ്പർ വ്യക്തമാക്കാമോ?"


_TEMPLATES: dict[str, ReplyTemplates] = {
    "ml-IN": ReplyTemplates(
        clarification="ക്ഷമിക്കണം, ഏത് തീയതിയും സമയവുമാണ് ഉദ്ദേശിച്ചത് എന്ന് വ്യക്തമാക്കാമോ?",
        unresolved=(
            "ക്ഷമിക്കണം, സമയം മനസ്സിലാക്കാൻ കഴിഞ്ഞില്ല. "
            "ഒരു ഹ്യൂമൻ അസിസ്റ്റന്റിലേക്ക് മാറ്റാം."
        ),
        available="{date} {time}-ന് സമയം ലഭ്യമാണ്.",
        nearest=(
            "{date} {time}-ന് സമയം ലഭ്യമല്ല; "
            "അടുത്ത ഒഴിവുള്ള സമയം {slot} ആണ്."
        ),
        confirming=(
            "{name}, {date} {time}-ന് {clinic}-ൽ അപ്പോയിന്റ്മെന്റ് "
            "ഉറപ്പാക്കാമോ?"
        ),
        booking_failed="ബുക്കിംഗ് ഉറപ്പാക്കാൻ കഴിഞ്ഞില്ല ({status}).",
        booked=(
            "{name}, {clinic}-ൽ {slot} സമയത്തേക്ക് അപ്പോയിന്റ്മെന്റ് "
            "ബുക്ക് ചെയ്തു (റഫറൻസ് {reference}). നന്ദി!"
        ),
        rejected="ബുക്കിംഗ് ഉറപ്പിച്ചിട്ടില്ല. വേറെ തീയതിയോ സമയമോ പരിശോധിക്കാമോ?",
        transfer="ഒരു ഹ്യൂമൻ ഓപ്പറേറ്ററിലേക്ക് മാറ്റുന്നു.",
        concluded="ഈ കോൾ അവസാനിച്ചു.",
        closed_day="{date} ക്ലിനിക് അടച്ചിരിക്കുന്നു; അടുത്ത ദിവസം പരിശോധിക്കുന്നു.",
        all_taken="{date}-ൽ എല്ലാ അപ്പോയിന്റ്മെന്റുകളും ബുക്ക് ചെയ്തിട്ടുണ്ട്.",
        no_open_day="അടുത്ത ഒരാഴ്ചയിൽ ഒരു ഓപ്പൺ ക്ലിനിക് ദിവസവും കണ്ടെത്തിയില്ല.",
        hangup="ഉപഭോക്താവ് അഭ്യർത്ഥന പൂർത്തിയാക്കുന്നതിന് മുമ്പ് കോൾ വിച്ഛേദിച്ചു.",
        thanks="നന്ദി, വീണ്ടും വിളിക്കുക.",
        ask_name="നന്ദി. ആരുടെ പേരിലാണ് അപ്പോയിന്റ്മെന്റ് ബുക്ക് ചെയ്യേണ്ടത്?",
        cancelled="{clinic}-ൽ {reference}-ാം നമ്പർ അപ്പോയിന്റ്മെന്റ് വിജയകരമായി റദ്ദാക്കി. നന്ദി!",
        cancel_not_found="ക്ഷമിക്കണം, ഈ റഫറൻസിൽ അപ്പോയിന്റ്മെന്റ് കണ്ടെത്താൻ കഴിഞ്ഞില്ല.",
        ask_cancel_ref="അപ്പോയിന്റ്മെന്റ് റദ്ദാക്കാൻ ദയവായി ബുക്കിംഗ് റഫറൻസ് നമ്പർ വ്യക്തമാക്കാമോ?",
    ),
    "hi-IN": ReplyTemplates(
        clarification="क्षमा करें, कृपया बताइए कि आप कौन सी तारीख और समय चाहते हैं?",
        unresolved=(
            "क्षमा करें, मैं अनुरोधित तारीख और समय समझ नहीं सका। "
            "एक सहायक से जोड़ रहा हूँ।"
        ),
        available="{date} को {time} बजे स्लॉट उपलब्ध है।",
        nearest="{date} को {time} बजे स्लॉट उपलब्ध नहीं है; निकटतम उपलब्ध स्लॉट {slot} है।",
        confirming="{name}, {clinic} में {date} को {time} बजे अपॉइंटमेंट की पुष्टि करें? क्या मैं बुक करूँ?",
        booking_failed="बुकिंग की पुष्टि नहीं हो सकी ({status})।",
        booked=(
            "{name}, {clinic} में {slot} पर अपॉइंटमेंट बुक हो गया है "
            "(संदर्भ {reference})। धन्यवाद!"
        ),
        rejected="बुकिंग की पुष्टि नहीं हुई। क्या आप कोई दूसरी तारीख या समय देखना चाहेंगे?",
        transfer="मैं आपको एक मानव ऑपरेटर से जोड़ रहा हूँ।",
        concluded="यह कॉल समाप्त हो चुकी है।",
        closed_day="{date} को क्लिनिक बंद है; अगला दिन देख रहा हूँ।",
        all_taken="{date} को सभी अपॉइंटमेंट बुक हो चुके हैं।",
        no_open_day="अगले एक सप्ताह में कोई खुला क्लिनिक दिन नहीं मिला।",
        hangup="कॉलर ने अनुरोध पूरा होने से पहले कॉल काट दी।",
        thanks="धन्यवाद, फिर से कॉल करें।",
    ),
    "mr-IN": ReplyTemplates(
        clarification="क्षमा करा, कृपया सांगा तुम्हाला कोणती तारीख आणि वेळ हवी आहे?",
        unresolved=(
            "क्षमा करा, मला विनंती केलेली तारीख आणि वेळ समजली नाही. "
            "मी तुम्हाला मानवी सहाय्यकाकडे जोडत आहे."
        ),
        available="{date} रोजी {time} वाजता स्लॉट उपलब्ध आहे.",
        nearest="{date} रोजी {time} वाजता स्लॉट उपलब्ध नाही; सर्वात जवळचा उपलब्ध स्लॉट {slot} आहे.",
        confirming="{name}, {clinic} मध्ये {date} रोजी {time} वाजता अपॉइंटमेंट निश्चित करू का?",
        booking_failed="बुकिंग निश्चित करता आली नाही ({status}).",
        booked=(
            "{name}, {clinic} मध्ये {slot} ला अपॉइंटमेंट बुक झाली आहे "
            "(संदर्भ {reference}). धन्यवाद!"
        ),
        rejected="बुकिंग निश्चित झाली नाही. दुसरी तारीख किंवा वेळ पाहायची का?",
        transfer="मी तुम्हाला मानवी ऑपरेटरकडे जोडत आहे.",
        concluded="हा कॉल संपला आहे.",
        closed_day="{date} रोजी क्लिनिक बंद आहे; पुढचा दिवस पाहत आहे.",
        all_taken="{date} रोजी सर्व अपॉइंटमेंट बुक झाल्या आहेत.",
        no_open_day="पुढील आठवड्यात कोणताही खुला क्लिनिक दिवस सापडला नाही.",
        hangup="कॉलरने विनंती पूर्ण होण्यापूर्वी कॉल कापला.",
        thanks="धन्यवाद, पुन्हा कॉल करा.",
    ),
    "bn-IN": ReplyTemplates(
        clarification="দুঃখিত, আপনি কোন তারিখ ও সময় চান তা বলবেন কি?",
        unresolved=(
            "দুঃখিত, আমি তারিখ ও সময় বুঝতে পারিনি। "
            "একজন মানব সহকারীর সাথে যুক্ত করছি।"
        ),
        available="{date} তারিখে {time} টায় স্লট পাওয়া যাচ্ছে।",
        nearest="{date} তারিখে {time} টায় স্লট নেই; নিকটতম স্লট {slot}।",
        confirming="{name}, {clinic}-এ {date} তারিখে {time} টায় অ্যাপয়েন্টমেন্ট নিশ্চিত করব?",
        booking_failed="বুকিং নিশ্চিত করা যায়নি ({status})।",
        booked=(
            "{name}, {clinic}-এ {slot}-এ অ্যাপয়েন্টমেন্ট বুক হয়েছে "
            "(রেফারেন্স {reference})। ধন্যবাদ!"
        ),
        rejected="বুকিং নিশ্চিত হয়নি। অন্য তারিখ বা সময় দেখবেন?",
        transfer="একজন মানব অপারেটরের সাথে যুক্ত করছি।",
        concluded="এই কল শেষ হয়েছে।",
        closed_day="{date} তারিখে ক্লিনিক বন্ধ; পরের দিন দেখছি।",
        all_taken="{date} তারিখে সব অ্যাপয়েন্টমেন্ট বুক হয়ে গেছে।",
        no_open_day="আগামী এক সপ্তাহে কোনো খোলা ক্লিনিক দিন পাওয়া যায়নি।",
        hangup="কলার অনুরোধ শেষ করার আগেই কল কেটে দিয়েছেন।",
        thanks="ধন্যবাদ, আবার কল করুন।",
    ),
    "ta-IN": ReplyTemplates(
        clarification="மன்னிக்கவும், நீங்கள் விரும்பும் தேதியும் நேரமும் என்ன என்று சொல்ல முடியுமா?",
        unresolved=(
            "மன்னிக்கவும், தேதி மற்றும் நேரத்தைப் புரிந்துகொள்ள முடியவில்லை. "
            "ஒரு மனித உதவியாளரிடம் மாற்றுகிறேன்."
        ),
        available="{date} அன்று {time} மணிக்கு இடம் உள்ளது.",
        nearest="{date} அன்று {time} மணிக்கு இடம் இல்லை; அருகிலுள்ள இடம் {slot}.",
        confirming="{name}, {clinic} இல் {date} அன்று {time} மணிக்கு சந்திப்பை உறுதிசெய்யவா?",
        booking_failed="முன்பதிவை உறுதிசெய்ய முடியவில்லை ({status}).",
        booked=(
            "{name}, {clinic} இல் {slot} மணிக்கு சந்திப்பு பதிவு செய்யப்பட்டது "
            "(குறிப்பு {reference}). நன்றி!"
        ),
        rejected="முன்பதிவு உறுதிசெய்யப்படவில்லை. வேறு தேதி அல்லது நேரத்தைப் பார்க்கவா?",
        transfer="ஒரு மனித இயக்குநரிடம் மாற்றுகிறேன்.",
        concluded="இந்த அழைப்பு முடிந்துவிட்டது.",
        closed_day="{date} அன்று கிளினிக் மூடப்பட்டுள்ளது; அடுத்த நாளைப் பார்க்கிறேன்.",
        all_taken="{date} அன்று அனைத்து சந்திப்புகளும் பதிவாகிவிட்டன.",
        no_open_day="அடுத்த வாரத்தில் திறந்த கிளினிக் நாள் எதுவும் கிடைக்கவில்லை.",
        hangup="அழைப்பாளர் கோரிக்கையை முடிக்கும் முன் அழைப்பைத் துண்டித்தார்.",
        thanks="நன்றி, மீண்டும் அழைக்கவும்.",
    ),
    "te-IN": ReplyTemplates(
        clarification="క్షమించండి, మీకు కావాల్సిన తేదీ మరియు సమయం చెప్పగలరా?",
        unresolved=(
            "క్షమించండి, తేదీ మరియు సమయాన్ని అర్థం చేసుకోలేకపోయాను. "
            "మానవ సహాయకుడికి బదిలీ చేస్తున్నాను."
        ),
        available="{date}న {time} గంటలకు స్లాట్ అందుబాటులో ఉంది.",
        nearest="{date}న {time} గంటలకు స్లాట్ లేదు; దగ్గరలోని స్లాట్ {slot}.",
        confirming="{name}, {clinic}లో {date}న {time} గంటలకు అపాయింట్‌మెంట్ నిర్ధారించాలా?",
        booking_failed="బుకింగ్ నిర్ధారించలేకపోయాము ({status}).",
        booked=(
            "{name}, {clinic}లో {slot}కు అపాయింట్‌మెంట్ బుక్ అయింది "
            "(సూచన {reference}). ధన్యవాదాలు!"
        ),
        rejected="బుకింగ్ నిర్ధారించబడలేదు. వేరే తేదీ లేదా సమయం చూడాలా?",
        transfer="మానవ ఆపరేటర్‌కి బదిలీ చేస్తున్నాను.",
        concluded="ఈ కాల్ ముగిసింది.",
        closed_day="{date}న క్లినిక్ మూసివేయబడింది; తర్వాతి రోజు చూస్తున్నాను.",
        all_taken="{date}న అన్ని అపాయింట్‌మెంట్‌లు బుక్ అయ్యాయి.",
        no_open_day="తదుపరి వారంలో ఏ క్లినిక్ రోజు తెరిచి లేదు.",
        hangup="కాలర్ అభ్యర్థన పూర్తి కాకముందే కాల్ కట్ చేశారు.",
        thanks="ధన్యవాదాలు, మళ్లీ కాల్ చేయండి.",
    ),
    "kn-IN": ReplyTemplates(
        clarification="ಕ್ಷಮಿಸಿ, ನಿಮಗೆ ಬೇಕಾದ ದಿನಾಂಕ ಮತ್ತು ಸಮಯವನ್ನು ತಿಳಿಸಬಹುದೇ?",
        unresolved=(
            "ಕ್ಷಮಿಸಿ, ದಿನಾಂಕ ಮತ್ತು ಸಮಯವನ್ನು ಅರ್ಥಮಾಡಿಕೊಳ್ಳಲಾಗಲಿಲ್ಲ. "
            "ಮಾನವ ಸಹಾಯಕರಿಗೆ ವರ್ಗಾಯಿಸುತ್ತಿದ್ದೇನೆ."
        ),
        available="{date} ರಂದು {time} ಕ್ಕೆ ಸ್ಲಾಟ್ ಲಭ್ಯವಿದೆ.",
        nearest="{date} ರಂದು {time} ಕ್ಕೆ ಸ್ಲಾಟ್ ಇಲ್ಲ; ಹತ್ತಿರದ ಸ್ಲಾಟ್ {slot}.",
        confirming="{name}, {clinic} ನಲ್ಲಿ {date} ರಂದು {time} ಕ್ಕೆ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ದೃಢೀಕರಿಸಬೇಕೇ?",
        booking_failed="ಬುಕಿಂಗ್ ದೃಢೀಕರಿಸಲಾಗಲಿಲ್ಲ ({status}).",
        booked=(
            "{name}, {clinic} ನಲ್ಲಿ {slot} ಕ್ಕೆ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಆಗಿದೆ "
            "(ಉಲ್ಲೇಖ {reference}). ಧನ್ಯವಾದಗಳು!"
        ),
        rejected="ಬುಕಿಂಗ್ ದೃಢೀಕರಿಸಲಿಲ್ಲ. ಬೇರೆ ದಿನಾಂಕ ಅಥವಾ ಸಮಯ ನೋಡಬೇಕೇ?",
        transfer="ಮಾನವ ಆಪರೇಟರ್‌ಗೆ ವರ್ಗಾಯಿಸುತ್ತಿದ್ದೇನೆ.",
        concluded="ಈ ಕರೆ ಮುಗಿದಿದೆ.",
        closed_day="{date} ರಂದು ಕ್ಲಿನಿಕ್ ಮುಚ್ಚಲಾಗಿದೆ; ಮುಂದಿನ ದಿನ ನೋಡುತ್ತಿದ್ದೇನೆ.",
        all_taken="{date} ರಂದು ಎಲ್ಲಾ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್‌ಗಳು ಬುಕ್ ಆಗಿವೆ.",
        no_open_day="ಮುಂದಿನ ವಾರದಲ್ಲಿ ಯಾವುದೇ ತೆರೆದ ಕ್ಲಿನಿಕ್ ದಿನ ಸಿಗಲಿಲ್ಲ.",
        hangup="ಕರೆದವರು ವಿನಂತಿ ಪೂರ್ಣಗೊಳ್ಳುವ ಮೊದಲು ಕರೆ ಕಡಿತಗೊಳಿಸಿದರು.",
        thanks="ಧನ್ಯವಾದಗಳು, ಮತ್ತೆ ಕರೆ ಮಾಡಿ.",
    ),
    "gu-IN": ReplyTemplates(
        clarification="માફ કરશો, તમે કઈ તારીખ અને સમય ઈચ્છો છો તે જણાવશો?",
        unresolved=(
            "માફ કરશો, તારીખ અને સમય સમજી શક્યો નથી. "
            "માનવ સહાયક સાથે જોડું છું."
        ),
        available="{date} ના રોજ {time} વાગ્યે સ્લોટ ઉપલબ્ધ છે.",
        nearest="{date} ના રોજ {time} વાગ્યે સ્લોટ નથી; નજીકનો સ્લોટ {slot} છે.",
        confirming="{name}, {clinic} માં {date} ના રોજ {time} વાગ્યે અપોઈન્ટમેન્ટ નિશ્ચિત કરું?",
        booking_failed="બુકિંગ નિશ્ચિત થઈ શક્યું નથી ({status}).",
        booked=(
            "{name}, {clinic} માં {slot} વાગ્યે અપોઈન્ટમેન્ટ બુક થઈ છે "
            "(સંદર્ભ {reference}). આભાર!"
        ),
        rejected="બુકિંગ નિશ્ચિત થયું નથી. બીજી તારીખ કે સમય જોવો છે?",
        transfer="હું તમને માનવ ઓપરેટર સાથે જોડું છું.",
        concluded="આ કૉલ પૂરો થઈ ગયો છે.",
        closed_day="{date} ના રોજ ક્લિનિક બંધ છે; આગલો દિવસ જોઈ રહ્યો છું.",
        all_taken="{date} ના રોજ બધી અપોઈન્ટમેન્ટ બુક થઈ ગઈ છે.",
        no_open_day="આગલા અઠવાડિયામાં કોઈ ખુલ્લો ક્લિનિક દિવસ મળ્યો નથી.",
        hangup="કૉલરે વિનંતી પૂરી કરતાં પહેલાં કૉલ કાપી નાખ્યો.",
        thanks="આભાર, ફરી કૉલ કરો.",
    ),
    "pa-IN": ReplyTemplates(
        clarification="ਮਾਫ਼ ਕਰਨਾ, ਤੁਸੀਂ ਕਿਹੜੀ ਤਾਰੀਖ਼ ਅਤੇ ਸਮਾਂ ਚਾਹੁੰਦੇ ਹੋ ਦੱਸ ਸਕਦੇ ਹੋ?",
        unresolved=(
            "ਮਾਫ਼ ਕਰਨਾ, ਮੈਂ ਤਾਰੀਖ਼ ਅਤੇ ਸਮਾਂ ਸਮਝ ਨਹੀਂ ਸਕਿਆ। "
            "ਮਨੁੱਖੀ ਸਹਾਇਕ ਨਾਲ ਜੋੜ ਰਿਹਾ ਹਾਂ।"
        ),
        available="{date} ਨੂੰ {time} ਵਜੇ ਸਲਾਟ ਉਪਲਬਧ ਹੈ।",
        nearest="{date} ਨੂੰ {time} ਵਜੇ ਸਲਾਟ ਨਹੀਂ ਹੈ; ਸਭ ਤੋਂ ਨੇੜਲਾ ਸਲਾਟ {slot} ਹੈ।",
        confirming="{name}, {clinic} ਵਿੱਚ {date} ਨੂੰ {time} ਵਜੇ ਅਪਾਇੰਟਮੈਂਟ ਪੱਕੀ ਕਰਾਂ?",
        booking_failed="ਬੁਕਿੰਗ ਪੱਕੀ ਨਹੀਂ ਹੋ ਸਕੀ ({status})।",
        booked=(
            "{name}, {clinic} ਵਿੱਚ {slot} ਵਜੇ ਅਪਾਇੰਟਮੈਂਟ ਬੁੱਕ ਹੋ ਗਈ ਹੈ "
            "(ਹਵਾਲਾ {reference})। ਧੰਨਵਾਦ!"
        ),
        rejected="ਬੁਕਿੰਗ ਪੱਕੀ ਨਹੀਂ ਹੋਈ। ਹੋਰ ਤਾਰੀਖ਼ ਜਾਂ ਸਮਾਂ ਵੇਖਣਾ ਹੈ?",
        transfer="ਮੈਂ ਤੁਹਾਨੂੰ ਮਨੁੱਖੀ ਆਪਰੇਟਰ ਨਾਲ ਜੋੜ ਰਿਹਾ ਹਾਂ।",
        concluded="ਇਹ ਕਾਲ ਖ਼ਤਮ ਹੋ ਚੁੱਕੀ ਹੈ।",
        closed_day="{date} ਨੂੰ ਕਲੀਨਿਕ ਬੰਦ ਹੈ; ਅਗਲਾ ਦਿਨ ਵੇਖ ਰਿਹਾ ਹਾਂ।",
        all_taken="{date} ਨੂੰ ਸਾਰੀਆਂ ਅਪਾਇੰਟਮੈਂਟਾਂ ਬੁੱਕ ਹੋ ਚੁੱਕੀਆਂ ਹਨ।",
        no_open_day="ਅਗਲੇ ਹਫ਼ਤੇ ਕੋਈ ਖੁੱਲ੍ਹਾ ਕਲੀਨਿਕ ਦਿਨ ਨਹੀਂ ਮਿਲਿਆ।",
        hangup="ਕਾਲਰ ਨੇ ਬੇਨਤੀ ਪੂਰੀ ਹੋਣ ਤੋਂ ਪਹਿਲਾਂ ਕਾਲ ਕੱਟ ਦਿੱਤੀ।",
        thanks="ਧੰਨਵਾਦ, ਦੁਬਾਰਾ ਕਾਲ ਕਰੋ।",
    ),
    "en-IN": ReplyTemplates(
        clarification="Sorry, could you please clarify which date and time you prefer?",
        unresolved=(
            "Sorry, I could not understand the requested date and time. "
            "Transferring to an assistant."
        ),
        available="{date} at {time} is available.",
        nearest="{date} at {time} is taken; the nearest open slot is {slot}.",
        confirming="{name}, {date} at {time}, {clinic}. Shall I book it?",
        booking_failed="The booking could not be confirmed ({status}).",
        booked=(
            "{name}, an appointment at {clinic} has been booked on {slot} "
            "(reference {reference}). Thank you!"
        ),
        rejected="Booking was not confirmed. Would you like to check a different date or time?",
        transfer="Transferring to a human operator.",
        concluded="This call has already concluded.",
        closed_day="The clinic is closed on {date}; checking the next day.",
        all_taken="All appointments are taken on {date}.",
        no_open_day="No open clinic day was found in the next week.",
        hangup="Caller hung up before completing the request.",
        thanks="Thank you, please call again.",
        ask_name="Thank you. Could you please share your name for the booking?",
        cancelled=(
            "Your appointment at {clinic} (reference {reference}) has been "
            "successfully cancelled. Thank you!"
        ),
        cancel_not_found="Sorry, no booking was found matching that reference.",
        ask_cancel_ref="Could you please share your booking reference number to cancel?",
    ),
}


def templates_for(language: str | None) -> ReplyTemplates:
    code = normalize_language(language) or DEFAULT_LANGUAGE
    return _TEMPLATES.get(code, _TEMPLATES[DEFAULT_LANGUAGE])
