// ── Effects-lite (?lite=1): sets the class consumed by the effects-lite CSS
if(new URLSearchParams(location.search).has('lite')){document.documentElement.classList.add('effects-lite');}
// Pause ticker marquees while the tab is hidden (saves compositor work)
document.addEventListener('visibilitychange',()=>document.body.classList.toggle('tab-hidden',document.hidden));
// ── i18n ─────────────────────────────────────────────────────────────────────
const STRINGS = {
  tr:{
    newChat:'Yeni sohbet', chats:'Sohbetler', mem:'Hafıza', memTitle:'Hafıza',
    ph:'Bir şey sor…',
    welcomeTitle:'piSynapse', welcomeSub:'Özel. Yerel. Senin.\nTüm veriler Pi\'nde kalır.',
    noChats:'Henüz sohbet yok', chatPrefix:'Sohbet', del:'Sil', noMem:'Henüz hafıza yok',
    authNeeded:'Bağlantı doğrulanamadı (API anahtarı geçersiz veya eksik)',
    authEnter:'Anahtarı yeniden gir',
    serverMisconf:'Sunucu API_KEY olmadan çalışıyor — .env dosyasında API_KEY ayarlayın.',
    noMemNote:'Konuşurken paylaştığın önemli detaylar burada tutulur.', loading:'Yükleniyor…',
    connErr:'Sunucuya ulaşılamadı', errConnLost:'Sunucuyla bağlantı kurulamadı. Lütfen tekrar dene.',
    errContextTooLong:'Bağlam çok uzun olduğu için model yanıt üretemedi. Lütfen yeni bir sohbet açıp tekrar dene.',
    delErr:'Sohbet silinemedi', thinkOn:'Think modu açık',
    thinkOff:'Think modu kapalı', copy:'Kopyala', copied:'Kopyalandı', emailConfirm:'E-posta Gönder',
    emptyReply:'Yanıt alınamadı — model boş cevap döndürdü, lütfen tekrar dene.',
    delConfirm:'Etkinliği Sil', chatDelConfirm:'Sohbeti Sil', memDelConfirm:'Hafızayı Sil',
    updateEventConfirm:'Etkinliği Güncelle', noteDelConfirm:'Notu Sil', taskDoneConfirm:'Görevi Tamamla', taskDelConfirm:'Görevi Sil',
    noteId:'Not ID', taskUid:'Görev', noteName:'Not Adı', taskName:'Görev Adı', eventNewSummary:'Yeni Başlık', eventNewTime:'Yeni Başlangıç Saati', eventNewDur:'Yeni Süre (dk)',
    confirmAction:'Onayla',
    emailTo:'Kime', emailSubj:'Konu', emailBody:'İçerik', emailCc:'Cc', emailBcc:'Bcc', delEventName:'Etkinlik',
    chatDelName:'Silinecek Sohbet', memDelContent:'Silinecek Bilgi', warnEmail:'Bu işlem geri alınamaz.',
    warnDel:'Silme işlemi geri alınamaz.', warnChatDel:'Bu sohbetin geçmişi veritabanından kalıcı olarak temizlenecektir.',
    warnMemDel:'Bu kayıt modelin uzun vadeli hafızasından kalıcı olarak silinecektir.', cancel:'İptal',
    confirm:'Gönder', confirmDel:'Sil', noEvents:'Bugün etkinlik yok',
    you:'Sen', topNew:'Yeni', feelsLike:'Hissedilen',
    settings:'Ayarlar', settingsTitle:'Ayarlar', settingsSaved:'Ayarlar kaydedildi',
     settingsRestart:'Bazı ayarlar sunucu yeniden başlatıldığında tam etkili olur.',
    settingsCancel:'İptal', settingsSave:'Kaydet',
    themeLabel:'Tema Rengi', langLabel:'Dil',
    glassLabel:'Cam Efekti',
    minimalLabel:'Sade Görünüm', minimalDesc:'Mesaj başlarındaki gönderen adı ve zaman etiketi gizlenir.',
    amoledLabel:'AMOLED (saf siyah)', amoledDesc:'OLED panellerde tam siyah arkaplan — pil dostu, daha derin kontrast.',
    fontLabel:'Yazı Tipi',
    obBadge:'Kurulum', obS1T:'Hoş geldin 👋', obS1S:'piSynapse tamamen telefonda çalışır — sohbetlerin ve hafızan cihazda kalır.', obS1B:'Başla',
    obS2T:'İzinler', obS2S:'Deneyimi zenginleştirmek için birkaç izin isteyeceğiz (dilersen atla).', obPermCal:'Takvim', obPermCalS:'Etkinlik oluştur/güncelle', obPermMic:'Mikrofon', obPermMicS:'Sesli komut ve dikte', obPermLoc:'Konum', obPermLocS:'Hava durumu için şehir tespiti', obGrant:'İzin ver', obGranted:'Verildi', obSkipPerm:'İzinleri atla',
    obS3T:'Kişisel bilgiler', obS3S:'Asistanı sana göre özelleştirelim. İstersen boş bırak.', obName:'Adın', obNamePh:'örn. Salih', obCity:'Şehir', obCityPh:'örn. İstanbul', obAsync:'Asistan adı', obAsyncPh:'örn. Selim', optional:'opsiyonel', obCityDetecting:'Konumdan şehir algılanıyor…',
    obS4T:'Model durumu', obS4S:'Yanıtlan üreten yerel model kontrol ediliyor…', obModelOk:'Model yüklü ve hazır ✓', obModelNone:'Yerel model bulunamadı. Ayarlar → Zeka üzerinden bir .litertlm dosyası seç veya ekle.', obModelLoading:'Model yükleniyor…', obModelHint:'Model çok yıllık bir dosyadır (2.5GB+); ilk yükleme birkaç dakika sürebilir.',
    obModelDown:'Modeli indir', obModelDownCustom:'Kendi adresinden indir', obModelDownUrl:'Bu adresten indir', obModelDownStart:'İndirme başlatılıyor…', obModelPct:'İndiriliyor… %s', obModelDownDone:'İndirme tamamlandı, model hazırlanıyor…', obModelDownFail:'İndirme başarısız oldu', obModelCancel:'İptal',
    obS6T:'Sunucu', obS6S:'Bu cihazı bir piSynapse sunucusuna bağla (isteğe bağlı). Boş bırakıp atlayabilir, sonradan Ayarlar → Sunucu üzerinden düzenleyebilirsin.', obS6Url:'Sunucu adresi', obS6UrlPh:'örn. https://pisynapse.local', obS6Key:'API anahtarı', obS6KeyPh:'Sunucunun API_KEY bilgisi', obS6User:'Sunucu kullanıcı', obS6UserPh:'Sunucudaki kullanıcı kimliği', obS6Hint:'API anahtarı sunucunun .env dosyasındaki API_KEY değeridir. Tarayıcıda sunucu adresi zaten açtığın adresle doldurulur.',
    obS5T:'Kısa tanıtım', obS5S:'Birkaç ipucu:', obTip1:'Kenar çubuğu: sohbet geçmişi ve hafıza', obTip2:'Yeni sohbeti üstteki + ile aç', obTip3:'Think modu düşünme seviyesini ayarlar', obTip4:'Ayarlar: tema, dil, font, AMOLED, model', obDone:'Kullanmaya başla',
    advanced:'Gelişmiş Ayarlar',
    setServerUrl:'Sunucu adresi', setServerUrlDesc:'Bu sayfanın erişildiği konum. Farklı bir piSynapse sunucusu kullanıyorsan burayı düzenle.', setServerUrlPh:'örn. https://pisynapse.local',
    setApiKeyLabel:'API anahtarı', setApiKeyDesc:'Sunucunun .env dosyasındaki API_KEY değeri ile eşleşmelidir.', setApiKeyPh:'Sunucudaki API_KEY değerinizi girin', setSrvHint:'Bu adres, tarayıcıda açtığın sayfanın kaynağı olarak kullanılır.',
    micDenied:'Mikrofon izni reddedildi', transcribeErr:'Ses tanıma başarısız oldu',
    micHttps:'Mikrofon HTTPS gerektirir. HTTPS ile erişin veya localhost kullanın.',
    micTryingWhisper:'Whisper deneniyor…',
    micTryingGemma4:'Gemma4 deneniyor…',
    micTryingBrowser:'Tarayıcı ses tanıma deneniyor…',
    micNoEngine:'Ses tanıma kullanılamıyor',
    ttsErr:'Sesli çıkış başarısız oldu',
    apiKeyPrompt:'API anahtarını girin (sunucu .env dosyasındaki API_KEY değeri):',
    searchPlaceholder:'Ara…', search:'Ara',
    compact:'Dar',
    thinkTitle:'Think modu',
    thinkNone:'Kapalı', thinkMin:'Min', thinkLow:'Düşük', thinkMed:'Orta', thinkHigh:'Yüksek', thinkMax:'Maks',
    thinkingTitle:'Düşünme', thinkingLive:'Düşünüyor…',
    send:'Gönder', stopGen:'Üretimi durdur', stoppedMsg:'Yanıt durduruldu.', listenTitle:'Sesli oku',
    copyTitle:'Mesajı kopyala', copiedTitle:'Kopyalandı', regenTitle:'Yeniden üret',
    thinkEffortTitle:'Think seviyesi',
    toolAttempt:'deneme', toolCap:'tekrar sınırı',
    markWrong:'Yanlıştı', markDone:'İşaretlendi', markSave:'Kaydet',
    markErr:'İşaretleme kaydedilemedi', markLoadErr:'Araç grupları yüklenemedi',
    corrNoop:'Araç zaten bu grupta — düzeltme değil bu',
    markConfirm:'Doğruydu', markConfirmDone:'Onaylandı', markConfirmErr:'Onay kaydedilemedi',
    fbWhich:'Hangisi yanlıştı?',
    notePlaceholder:'Neden yanlıştı? (opsiyonel)…', noteSave:'Kaydet', noteCancel:'İptal',
    genRetryLabel:'Araç yanıtları sıkıştırılıp yeniden deneniyor…',
    genRetryLeak:'Araç çağrısı düzeltiliyor…',
    genRetryEscalate:'Gerekli araçlar etkinleştiriliyor…',
    verifFail:'İşlem doğrulanamadı, kontrol edin', clarifyAsked:'Kullanıcıdan bilgi istendi',
    noopInfo:'Hedef zaten yok, işlem yapılmadı'
  },
  en:{
    newChat:'New chat', chats:'Chats', mem:'Memory', memTitle:'Memory',
    ph:'Ask something…',
    welcomeTitle:'piSynapse', welcomeSub:'Private. Local. Yours.\nAll data stays on your Pi.',
    noChats:'No chats yet', chatPrefix:'Chat', del:'Delete', noMem:'No memories yet',
    authNeeded:'Connection failed (API key invalid or missing)',
    authEnter:'Re-enter key',
    serverMisconf:'The server is running without an API key — set API_KEY in .env.',
    noMemNote:'Important details you share will be structured here.', loading:'Loading…',
    connErr:'Could not reach server', errConnLost:'Could not connect to the server. Please try again.',
    errContextTooLong:'The model could not produce a reply because the context is too long. Please start a new chat and try again.',
    delErr:'Could not delete chat', thinkOn:'Think mode on',
    thinkOff:'Think mode off', copy:'Copy', copied:'Copied', emailConfirm:'Send Email',
    emptyReply:'No response received — the model returned an empty reply, please try again.',
    delConfirm:'Delete Event', chatDelConfirm:'Delete Chat', memDelConfirm:'Delete Memory',
    updateEventConfirm:'Update Event', noteDelConfirm:'Delete Note', taskDoneConfirm:'Complete Task', taskDelConfirm:'Delete Task',
    noteId:'Note ID', taskUid:'Task', noteName:'Note Name', taskName:'Task Name', eventNewSummary:'New Title', eventNewTime:'New Start Time', eventNewDur:'New Duration (min)',
    confirmAction:'Confirm',
    emailTo:'To', emailSubj:'Subject', emailBody:'Content', emailCc:'Cc', emailBcc:'Bcc', delEventName:'Event',
    chatDelName:'Chat to Delete', memDelContent:'Record to Delete', warnEmail:'This action cannot be undone.',
    warnDel:'Deletion cannot be undone.', warnChatDel:'This chat history will be permanently wiped from the database.',
    warnMemDel:'This record will be permanently erased from long-term memory.', cancel:'Cancel',
    confirm:'Send', confirmDel:'Delete', noEvents:'No events today',
    you:'You', topNew:'New', feelsLike:'Feels like',
    settings:'Settings', settingsTitle:'Settings', settingsSaved:'Settings saved',
    settingsRestart:'Some settings take full effect only after server restart.',
    settingsCancel:'Cancel', settingsSave:'Save',
    themeLabel:'Theme Color', langLabel:'Language',
    glassLabel:'Glass Effect',
    minimalLabel:'Minimal View', minimalDesc:'Hides sender names and timestamps above messages.',
    amoledLabel:'AMOLED (true black)', amoledDesc:'Pure-black background on OLED panels — battery friendly, deeper contrast.',
    fontLabel:'Font',
    obBadge:'Setup', obS1T:'Welcome 👋', obS1S:'piSynapse runs entirely on your phone — chats and memory stay on-device.', obS1B:'Get started',
    obS2T:'Permissions', obS2S:'We will ask for a few permissions to enrich the experience (you can skip).', obPermCal:'Calendar', obPermCalS:'Create/update events', obPermMic:'Microphone', obPermMicS:'Voice commands & dictation', obPermLoc:'Location', obPermLocS:'City detection for weather', obGrant:'Grant', obGranted:'Granted', obSkipPerm:'Skip permissions',
    obS3T:'Personal info', obS3S:'Let us tailor your assistant. You can leave these empty.', obName:'Your name', obNamePh:'e.g. Salih', obCity:'City', obCityPh:'e.g. Istanbul', obAsync:'Assistant name', obAsyncPh:'e.g. Selim', optional:'optional', obCityDetecting:'Detecting city from location…',
    obS4T:'Model status', obS4S:'Checking the local model that powers replies…', obModelOk:'Model is loaded and ready ✓', obModelNone:'No local model found. Pick or add a .litertlm file under Settings → Intelligence.', obModelLoading:'Model is loading…', obModelHint:'The model is a large file (2.5GB+); first load may take a couple minutes.',
    obModelDown:'Download model', obModelDownCustom:'Download from custom URL', obModelDownUrl:'Download from this URL', obModelDownStart:'Starting download…', obModelPct:'Downloading… %s', obModelDownDone:'Download complete, preparing model…', obModelDownFail:'Download failed', obModelCancel:'Cancel',
    obS6T:'Server', obS6S:'Connect this device to a piSynapse server (optional). Leave empty to skip; you can edit it later from Settings → Server.', obS6Url:'Server URL', obS6UrlPh:'e.g. https://pisynapse.local', obS6Key:'API key', obS6KeyPh:'Your server API_KEY', obS6User:'Server user', obS6UserPh:'Your user ID on the server', obS6Hint:'The API key is the API_KEY value in your server\'s .env file. In browser mode the server URL is pre-filled with the address you opened.',
    obS5T:'Quick tour', obS5S:'A few tips:', obTip1:'Sidebar: chat history and memory', obTip2:'Start a new chat with the + above', obTip3:'Think mode controls the reasoning level', obTip4:'Settings: theme, language, font, AMOLED, model', obDone:'Start using',
    advanced:'Advanced Settings',
    setServerUrl:'Server URL', setServerUrlDesc:'Where this page is served from. Edit if you use a different piSynapse server.', setServerUrlPh:'e.g. https://pisynapse.local',
    setApiKeyLabel:'API key', setApiKeyDesc:'Must match the API_KEY value in your server\'s .env file.', setApiKeyPh:'Enter your server API_KEY', setSrvHint:'This address is used as the origin of the page you opened in the browser.',
    micDenied:'Microphone permission denied', transcribeErr:'Transcription failed',
    micHttps:'Microphone requires HTTPS. Use HTTPS or localhost.',
    micTryingWhisper:'Trying Whisper…',
    micTryingGemma4:'Trying Gemma4…',
    micTryingBrowser:'Trying browser speech recognition…',
    micNoEngine:'Speech recognition unavailable',
    ttsErr:'Text-to-speech failed',
    apiKeyPrompt:'Enter API key (the API_KEY value from the server .env file):',
    searchPlaceholder:'Search…', search:'Search',
    compact:'Compact',
    thinkTitle:'Think mode',
    thinkNone:'Off', thinkMin:'Min', thinkLow:'Low', thinkMed:'Med', thinkHigh:'High', thinkMax:'Max',
    thinkingTitle:'Thinking', thinkingLive:'Thinking…',
    send:'Send', stopGen:'Stop generating', stoppedMsg:'Response stopped.', listenTitle:'Listen',
    copyTitle:'Copy message', copiedTitle:'Copied', regenTitle:'Regenerate',
    thinkEffortTitle:'Think effort',
    toolAttempt:'attempt', toolCap:'retry cap',
    markWrong:'Wrong', markDone:'Marked', markSave:'Save',
    markErr:'Could not save the marking', markLoadErr:'Could not load tool groups',
    corrNoop:'Tool is already in this group — not a correction',
    markConfirm:'Correct', markConfirmDone:'Confirmed', markConfirmErr:'Could not save the confirmation',
    fbWhich:'Which one was wrong?',
    notePlaceholder:'Why was it wrong? (optional)…', noteSave:'Save', noteCancel:'Cancel',
    genRetryLabel:'Compressing tool responses and retrying…',
    genRetryLeak:'Fixing a tool call…',
    genRetryEscalate:'Enabling the required tools…',
    verifFail:'Operation failed verification — please check', clarifyAsked:'Asked the user for details',
    noopInfo:'Target already gone, nothing to do'
  }
};

let lang  = localStorage.getItem('ps_lang') || ((navigator.language||'').toLowerCase().startsWith('tr') ? 'tr' : 'en');
let theme = localStorage.getItem('ps_theme') || 'orange';
let glass = localStorage.getItem('ps_glass') === '1';
let minimal = localStorage.getItem('ps_minimal') === '1';
let amoled = localStorage.getItem('ps_amoled') === '1';
let fontMode = localStorage.getItem('ps_font') || 'dmsans';
function enhanceSelect(sel){
  if(!sel || sel.dataset.enhanced) return;
  sel.dataset.enhanced = '1';
  sel.style.display = 'none';
  const wrap=document.createElement('div'); wrap.className='sel-wrap';
  const btn=document.createElement('button'); btn.type='button'; btn.className='sel-btn';
  const menu=document.createElement('div'); menu.className='sel-menu';
  sel.parentNode.insertBefore(wrap, sel);
  wrap.appendChild(btn); wrap.appendChild(menu); wrap.appendChild(sel);

  const options=()=>[...sel.options].map(o=>({v:o.value,t:o.textContent,s:o.selected}));
  const syncBtn=()=>{ const o=options().find(x=>x.s)||options()[0]; btn.textContent=o?o.t:''; };
  const buildMenu=()=>{
    menu.innerHTML=options().map(o=>`<div class="sel-opt${o.s?' on':''}" data-v="${esc(o.v)}">${esc(o.t)}</div>`).join('');
    syncBtn();
  };
  buildMenu();
  btn.addEventListener('click',e=>{
    e.stopPropagation();
    const willOpen=!wrap.classList.contains('open');
    document.querySelectorAll('.sel-wrap.open').forEach(w=>w.classList.remove('open'));
    if(willOpen){ wrap.classList.add('open'); menu.scrollTop=0; }
  });
  menu.addEventListener('click',e=>{
    const d=e.target.closest('.sel-opt'); if(!d) return;
    sel.value=d.dataset.v;
    sel.dispatchEvent(new Event('change'));
    buildMenu();
    wrap.classList.remove('open');
  });
  // keep the pretty control in sync when code sets sel.value directly
  sel.addEventListener('change', buildMenu);
}
function enhanceAllSelects(root){
  (root||document).querySelectorAll('#lang-select, #settings-form select').forEach(enhanceSelect);
}
document.addEventListener('click',()=>document.querySelectorAll('.sel-wrap.open').forEach(w=>w.classList.remove('open')));
document.addEventListener('keydown',e=>{
  if(e.key==='Escape') document.querySelectorAll('.sel-wrap.open').forEach(w=>w.classList.remove('open'));
});
// Press feedback that survives a quick tap: :active is too brief to paint on
// touch (it only reads as a visible effect while the finger is held). Mirroring
// the CTA buttons' :active styles, .tap-flash lingers ~250ms from pointerdown so
// even an instant tap shows the pressed glow, then clears on its own.
document.addEventListener('pointerdown', e => {
  const b = e.target.closest('.new-btn,.top-new-btn');
  if(!b) return;
  b.classList.add('tap-flash');
  clearTimeout(b._pflash);
  b._pflash = setTimeout(()=> b.classList.remove('tap-flash'), 250);
}, { passive: true });

function t(k){ return STRINGS[lang][k] || k; }

// WMO weather-code labels, localized client-side so the widget reads the UI
// language regardless of what the backend summarizes.
const WMO_LABELS = {
  tr:{0:'Açık',1:'Az bulutlu',2:'Parçalı bulutlu',3:'Kapalı',45:'Sisli',48:'Kırağılı sis',
      51:'Hafif çisenti',53:'Çisenti',55:'Yoğun çisenti',56:'Hafif donan çisenti',57:'Donan çisenti',
      61:'Hafif yağmur',63:'Yağmurlu',65:'Yoğun yağmur',66:'Hafif donan yağmur',67:'Donan yağmur',
      71:'Hafif kar',73:'Karlı',75:'Yoğun kar',77:'Kar tanesi',
      80:'Hafif sağanak',81:'Sağanak',82:'Şiddetli sağanak',85:'Kar sağanağı',86:'Yoğun kar sağanağı'},
  en:{0:'Clear',1:'Mostly clear',2:'Partly cloudy',3:'Overcast',45:'Foggy',48:'Rime fog',
      51:'Light drizzle',53:'Drizzle',55:'Dense drizzle',56:'Light freezing drizzle',57:'Freezing drizzle',
      61:'Light rain',63:'Rain',65:'Heavy rain',66:'Light freezing rain',67:'Freezing rain',
      71:'Light snow',73:'Snow',75:'Heavy snow',77:'Snow grains',
      80:'Light showers',81:'Showers',82:'Heavy showers',85:'Snow showers',86:'Heavy snow showers'},
};
function wmoLabel(code){
  const l = WMO_LABELS[lang] || WMO_LABELS.en;
  if(code != null){
    if(l[code]) return l[code];
    if(code >= 95 && code <= 99) return lang==='tr' ? ('Gök gürültülü' + (code >= 96 ? ' dolu' : '')) : ('Thunderstorm' + (code >= 96 ? ' with hail' : ''));
  }
  return lang === 'tr' ? 'Bilinmiyor' : 'Unknown';
}
function wmoIconKind(code){
  if(code == null) return 'unknown';
  if(code === 0) return 'clear';
  if(code === 1 || code === 2) return 'partly';
  if(code === 3) return 'cloud';
  if(code === 45 || code === 48) return 'fog';
  if(code >= 51 && code <= 57) return 'drizzle';
  if((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return 'rain';
  if((code >= 71 && code <= 77) || code === 85 || code === 86) return 'snow';
  if(code >= 95 && code <= 99) return 'storm';
  return 'unknown';
}

const TOOL_LABELS={
  tr:{get_weather:'Havaya bakıyorum', get_datetime:'Saate bakıyorum',
    create_calendar_event:'Etkinlik oluşturuyorum', list_calendar_events:'Takvimine bakıyorum',
    delete_calendar_event:'Etkinliği siliyorum', update_calendar_event:'Etkinliği güncelliyorum',
    find_free_slots:'Boş saatlerini arıyorum',
    list_emails:'E-postalarına bakıyorum', read_email:'E-postayı okuyorum',
    send_email:'E-posta gönderiyorum', search_emails:'E-postalarda arıyorum',
    save_memory:'Bunu hatırlıyorum', create_note:'Not oluşturuyorum',
    list_notes:'Notlarını listeliyorum', read_note:'Notu okuyorum',
    update_note:'Notu güncelliyorum', delete_note:'Notu siliyorum', search_notes:'Notlarda arıyorum',
    create_task:'Görev oluşturuyorum', list_tasks:'Görevlerini listeliyorum',
    complete_task:'Görevi tamamlıyorum', delete_task:'Görevi siliyorum', search_tasks:'Görevlerde arıyorum'},
  en:{get_weather:'Checking the weather', get_datetime:'Checking the time',
    create_calendar_event:'Creating an event', list_calendar_events:'Checking your calendar',
    delete_calendar_event:'Deleting an event', update_calendar_event:'Updating an event',
    find_free_slots:'Checking your free slots',
    list_emails:'Checking your emails', read_email:'Reading the email',
    send_email:'Sending an email', search_emails:'Searching your emails',
    save_memory:'Saving to memory', create_note:'Creating a note',
    list_notes:'Listing your notes', read_note:'Reading a note',
    update_note:'Updating a note', delete_note:'Deleting a note', search_notes:'Searching notes',
    create_task:'Creating a task', list_tasks:'Listing your tasks',
    complete_task:'Completing a task', delete_task:'Deleting a task', search_tasks:'Searching tasks'}
};
function toolLabel(n){ return (TOOL_LABELS[lang] && TOOL_LABELS[lang][n]) || n; }
// Compact per-tool names for the multi-tool correction chips — the full
// TOOL_LABELS verbs (e.g. "Etkinlik oluşturuyorum") are too long for pills.
const TOOL_SHORT={
  tr:{get_weather:'Hava', get_datetime:'Saat',
    create_calendar_event:'Takvim', list_calendar_events:'Takvim',
    delete_calendar_event:'Takvim', update_calendar_event:'Takvim', find_free_slots:'Saat',
    list_emails:'E-posta', read_email:'E-posta', send_email:'E-posta', search_emails:'E-posta',
    save_memory:'Hafıza', create_note:'Notlar', list_notes:'Notlar', read_note:'Notlar',
    update_note:'Notlar', delete_note:'Notlar', search_notes:'Notlar',
    create_task:'Görevler', list_tasks:'Görevler', complete_task:'Görevler',
    delete_task:'Görevler', search_tasks:'Görevler'},
  en:{get_weather:'Weather', get_datetime:'Time',
    create_calendar_event:'Calendar', list_calendar_events:'Calendar',
    delete_calendar_event:'Calendar', update_calendar_event:'Calendar', find_free_slots:'Time',
    list_emails:'Email', read_email:'Email', send_email:'Email', search_emails:'Email',
    save_memory:'Memory', create_note:'Notes', list_notes:'Notes', read_note:'Notes',
    update_note:'Notes', delete_note:'Notes', search_notes:'Notes',
    create_task:'Tasks', list_tasks:'Tasks', complete_task:'Tasks',
    delete_task:'Tasks', search_tasks:'Tasks'}
};
function toolShort(n){ return (TOOL_SHORT[lang] && TOOL_SHORT[lang][n]) || n; }

const GROUP_LABELS={
  tr:{calendar:'Takvim', tasks:'Görevler', memory:'Hafıza', email:'E-posta', notes:'Notlar', weather:'Hava Durumu'},
  en:{calendar:'Calendar', tasks:'Tasks', memory:'Memory', email:'Email', notes:'Notes', weather:'Weather'}
};
function groupLabel(g){ return (GROUP_LABELS[lang] && GROUP_LABELS[lang][g]) || g; }

let currentSid = null; let sessionList = []; let loading = false; let memOpen = false;
const SEND_ICON='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>';
const STOP_ICON='<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg>';
let userAborted=false;
let pendingAction = null; let tickerItems = []; let tickerIdx = 0; let typingEl = null;
const THINK_LEVELS = [
  {effort:'minimal', hint:{tr:'Hafif düşünme, hızlı yanıt.', en:'Light thinking, fast responses.'}},
  {effort:'low',     hint:{tr:'Düşük düşünme, hızlı yanıt.', en:'Low thinking, quick responses.'}},
  {effort:'medium',  hint:{tr:'Dengeli analiz ve hız.', en:'Balanced analysis and speed.'}},
  {effort:'high',    hint:{tr:'Daha derin analiz, daha yavaş yanıt.', en:'Deeper analysis, slower responses.'}},
  {effort:'xhigh',   hint:{tr:'En derin analiz, en yavaş yanıt.', en:'Deepest analysis, slowest responses.'}},
];
// litert 0.15 maps all enabled levels to the same token budget; the effort
// picker is hidden until per-level budgets land (litert b/514760339).
// Flip to true to re-enable the 5-level slider — backend chain already works.
// Note: the think button is currently a plain icon button (same as mic/attach);
// re-enabling the picker also requires restoring the split/caret markup + lv
// fill classes in #think-wrap (see git history).
const THINK_EFFORT_PICKER = false;
const THINK_EFFORTS = THINK_LEVELS.map(l => l.effort);
let thinkEffort = localStorage.getItem('ps_think_effort') || 'none';
if(thinkEffort !== 'none' && !THINK_EFFORTS.includes(thinkEffort)) thinkEffort = 'none';
let thinkMode = thinkEffort !== 'none';
let lastThinkEffort = thinkMode ? thinkEffort : 'medium';
let _cachedWeatherSummary = null; let _cachedWeatherRaw = null; let _cachedEvents = null;
let _cachedWeatherKind = null; let _cachedWeatherTemp = null; let _cachedWeatherCond = null; let _cachedWeatherWmo = null;

// ── Markdown, LaTeX & Copy (local parser) ─────────────────────────────────────
function esc(s){ return String(s||'').replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>').replace(/"/g,'"').replace(/'/g,'\''); }

// Minimal XSS sanitizer: native Sanitizer API (Baseline 2024) + textContent fallback
// XSS sanitizer: DOMPurify (battle-tested, self-hosted) with native
// Sanitizer API and textContent as progressive fallbacks. DOMPurify must run
// on the main thread (needs a real DOM), so markdown rendering is main-thread.
function sanitizeHTML(html) {
  if (!html) return '';
  if (window.DOMPurify) {
    try {
      return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
    } catch (e) {
      console.warn('DOMPurify failed, falling back:', e);
    }
  }
  if (window.Sanitizer) {
    try {
      const sanitizer = new Sanitizer();
      const div = document.createElement('div');
      div.innerHTML = html;
      sanitizer.sanitize(div);
      return div.innerHTML;
    } catch (e) {
      console.warn('Native Sanitizer failed, falling back:', e);
    }
  }
  const div = document.createElement('div');
  div.textContent = html;
  return div.innerHTML;
}

function parseMath(s) {
  const dict = {
    '\\rightarrow': '\u2192', '\\leftarrow': '\u2190', '\\Rightarrow': '\u21D2', '\\Leftarrow': '\u21D0',
    '\\leftrightarrow': '\u2194', '\\Leftrightarrow': '\u21D4', '\\times': '\u00D7', '\\div': '\u00F7',
    '\\leq': '\u2264', '\\geq': '\u2265', '\\neq': '\u2260', '\\approx': '\u2248', '\\pm': '\u00B1',
    '\\cdot': '\u00B7', '\\infty': '\u221E', '\\Delta': '\u0394', '\\alpha': '\u03B1', '\\beta': '\u03B2',
    '\\theta': '\u03B8', '\\pi': '\u03C0', '\\sigma': '\u03C3', '\\sum': '\u2211', '\\prod': '\u220F', '\\sqrt': '\u221A'
  };
  return s.replace(/\\[a-zA-Z]+/g, m => dict[m] || m);
}

function inl(s){
  s = esc(s);
  s = s.replace(/\*\*\*(.+?)\*\*\*/g,'<strong><em>$1</em></strong>');
  s = s.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g,'<em>$1</em>');
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, t, u) => { const safe=/^(https?:|mailto:)/i.test(u.trim()); return safe ? `<a href="${u}" target="_blank" rel="noopener">${t}</a>` : `[${t}](${u})`; });
  return s;
}

function copyCode(btn) {
  const codeEl = btn.closest('.code-wrapper').querySelector('code');
  if(!codeEl) return;
  const textToCopy = codeEl.innerText;
  const onSuccess = () => {
    const label = btn.querySelector('.copy-label');
    if (label) {
      const originalText = label.textContent;
      label.textContent = t('copied');
      btn.style.color = 'var(--success)';
      setTimeout(() => { label.textContent = originalText; btn.style.color = ''; }, 2000);
    }
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(textToCopy).then(onSuccess).catch(err => console.error("Copy error:", err));
  } else {
    const textArea = document.createElement("textarea");
    textArea.value = textToCopy;
    textArea.style.position = "fixed"; textArea.style.left = "-999999px"; textArea.style.top = "-999999px";
    document.body.appendChild(textArea); textArea.focus(); textArea.select();
    try { document.execCommand('copy'); onSuccess(); } catch (err) { console.error("Clipboard fallback error:", err); }
    document.body.removeChild(textArea);
  }
}

function stripMarkdown(text){
  if(!text) return '';
  return text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\*{1,3}([^*]+)\*{1,3}/g, '$1')
    .replace(/_{1,3}([^_]+)_{1,3}/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^[\-\*_]{3,}\s*$/gm, '')
    .replace(/^>\s*/gm, '')
    .replace(/^[\-\*\+]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .replace(/\|/g, ' ')
    .replace(/(?<!\w)[*_]{1,2}(?!\w)/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/ {2,}/g, ' ')
    .trim();
}

// Marked configuration: GitHub Flavored Markdown (tables, strikethrough, task
// lists) + "breaks" so single newlines render as <br> (chat-style, matches the
// old regex behavior). Link renderer adds target/rel; protocol safety is
// enforced downstream by sanitizeHTML()/DOMPurify.
function configMarked(){
  if(!window.marked || window._mdConfigured) return;
  marked.setOptions({ gfm:true, breaks:true });
  const renderer = new marked.Renderer();
  const link = renderer.link.bind(renderer);
  renderer.link = (href, title, text) => {
    const h = link(href, title, text);
    return h.replace('<a ', '<a target="_blank" rel="noopener noreferrer" ');
  };
  marked.use({ renderer });
  window._mdConfigured = true;
}

function renderMd(raw){
  if(!raw) return '';
  configMarked();
  const CB=[], IC=[], MATH=[];
  // markdown-inert placeholders: letters/digits only (no *_[]#` ) so marked
  // never mangles them; unique prefix avoids collisions with user text.
  const T = (kind,i)=> 'ZQMD'+kind+i+'ZQ';
  let s = String(raw);

  s = s.replace(/\$\$\n?([\s\S]*?)\n?\$\$/g, (_, math) => {
    MATH.push(`<div class="math-display">${parseMath(esc(math))}</div>`);
    return T('MB', MATH.length-1);
  });
  s = s.replace(/\$([^\$\n]+)\$/g, (_, math) => {
    MATH.push(`<span class="math-inline">${parseMath(esc(math))}</span>`);
    return T('MI', MATH.length-1);
  });
  s = s.replace(/```([\w]*)\n?([\s\S]*?)```/g, (_, lang, code)=>{
    const displayLang = lang ? lang.toUpperCase() : 'CODE';
    CB.push(`
      <div class="code-wrapper">
        <div class="code-header">
          <span class="lang">${esc(displayLang)}</span>
          <button class="copy-btn" onclick="copyCode(this)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg> <span class="copy-label">${t('copy')}</span>
          </button>
        </div>
        <pre><code>${esc(code.trimEnd())}</code></pre>
      </div>
    `);
    return T('CB', CB.length-1);
  });
  s = s.replace(/`([^`\n]+)`/g, (_,code)=>{
    IC.push(`<code>${esc(code)}</code>`);
    return T('IC', IC.length-1);
  });

  // Normalize leading bold-number list markers ("**1.** Foo") to plain
  // ordered-list markers ("1. Foo") so marked builds a real <ol> regardless of
  // whether the model emitted bold numbers (the old regex engine did NOT
  // produce <ol>, so CSS used list-style:none; marked does, and must not hide it).
  s = s.replace(/^(\s*)\*\*(\d+)[.)]\*\*(?=\s|$)/gm, '$1$2.');

  // Token-based parse (marked) replacing the old line-by-line regex parser.
  // Tables, nested lists, escaping, blockquotes and GFM all handled correctly.
  let r = window.marked && window.marked.parse ? sanitizeHTML(marked.parse(s)) : s;

  // Reinsert isolated content AFTER sanitization so classes/onclick survive.
  IC.forEach((c,i)=>{ r=r.split(T('IC',i)).join(c); });
  CB.forEach((c,i)=>{ r=r.split(T('CB',i)).join(c); });
  MATH.forEach((c,i)=>{
    r=r.split(T('MB',i)).join(c);
    r=r.split(T('MI',i)).join(c);
  });
  return r;
}

// ── Theme & Language Settings ──────────────────────────────────────────────────
const THEMES = [
  { id: 'orange', color: '#f0943a', label: { tr: 'Turuncu', en: 'Orange' } },
  { id: 'blue',   color: '#4d9ff5', label: { tr: 'Mavi',    en: 'Blue' } },
  { id: 'green',  color: '#3dbf65', label: { tr: 'Yesil',   en: 'Green' } },
  { id: 'purple', color: '#9578f5', label: { tr: 'Mor',     en: 'Purple' } },
  { id: 'red',    color: '#f05555', label: { tr: 'Kirmizi', en: 'Red' } },
  { id: 'black',  color: '#e9e9ec', label: { tr: 'Siyah',   en: 'Black' } },
];

function applyTheme(name){
  theme = name;
  document.body.classList.toggle('theme-orange', name === 'orange');
  document.body.classList.toggle('theme-blue', name === 'blue');
  document.body.classList.toggle('theme-green', name === 'green');
  document.body.classList.toggle('theme-purple', name === 'purple');
  document.body.classList.toggle('theme-red', name === 'red');
  document.body.classList.toggle('theme-black', name === 'black');
  localStorage.setItem('ps_theme', name);
  document.querySelectorAll('.theme-swatch').forEach(el => {
    el.classList.toggle('active', el.dataset.theme === name);
  });
}

function applyGlass(on){
  glass = on;
  document.body.classList.toggle('glass-mode', on);
  localStorage.setItem('ps_glass', on ? '1' : '0');
}

function applyMinimal(on){
  minimal = on;
  document.body.classList.toggle('minimal-chat', on);
  localStorage.setItem('ps_minimal', on ? '1' : '0');
}

function applyAmoled(on){
  amoled = on;
  document.body.classList.toggle('amoled', on);
  localStorage.setItem('ps_amoled', on ? '1' : '0');
}

function applyFont(f){
  fontMode = f;
  document.body.classList.toggle('font-system', f === 'system');
  localStorage.setItem('ps_font', f);
}

function renderThemeGrid(){
  const grid = document.getElementById('theme-grid');
  if(!grid) return;
  grid.innerHTML = THEMES.map(th =>
    `<div class="theme-swatch${theme===th.id?' active':''}" role="button" tabindex="0" data-theme="${th.id}"
          style="color:${th.color}" onclick="applyTheme('${th.id}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();applyTheme('${th.id}')}" aria-label="${th.label[lang]||th.id}"></div>`
  ).join('');
}

function applyLang(l){
  lang = l; document.documentElement.lang = l; localStorage.setItem('ps_lang', l);

  const newBtnLabel = document.getElementById('btn-new-text');
  if(newBtnLabel) newBtnLabel.textContent = t('newChat');
  document.getElementById('lbl-chats').textContent = t('chats');
  document.getElementById('lbl-mem').textContent = t('mem');
  const stBtn = document.getElementById('settings-btn');
  if(stBtn) stBtn.title = t('settings');
  document.getElementById('sidebar-mem-section').textContent = t('memTitle');
  document.getElementById('msg-input').placeholder = t('ph');
  document.getElementById('m-cancel').textContent = t('cancel');
  document.getElementById('lbl-top-new').textContent = t('topNew');
  document.getElementById('lbl-settings-title').textContent = t('settingsTitle');
  const lblAdv = document.getElementById('lbl-advanced');
  if(lblAdv) lblAdv.textContent = _sectionLabel('Advanced');
  document.getElementById('settings-cancel-btn').textContent = t('settingsCancel');
  document.getElementById('settings-save-btn').textContent = t('settingsSave');
  document.getElementById('settings-restart-notice').textContent = t('settingsRestart');
  const themeLabel = document.getElementById('lbl-theme-select');
  if(themeLabel) themeLabel.textContent = t('themeLabel');
  const langLabel = document.getElementById('lbl-lang-select');
  if(langLabel) langLabel.textContent = t('langLabel');
  const glassLabel = document.getElementById('lbl-glass-label');
  if(glassLabel) glassLabel.textContent = t('glassLabel');
  const glassToggle = document.getElementById('glass-toggle');
  if(glassToggle){ glassToggle.checked = glass; }

  const searchInput = document.getElementById('sess-search');
  if(searchInput) searchInput.placeholder = t('searchPlaceholder');
  const searchToggle = document.getElementById('search-toggle');
  if(searchToggle) searchToggle.title = t('search');
  const compactToggle = document.getElementById('compact-toggle');
  if(compactToggle) compactToggle.title = t('compact');
  const memBack = document.getElementById('mem-back');
  if(memBack) memBack.title = t('chats');
  document.getElementById('inline-think-btn').title = t('thinkTitle');
  const tpTitle = document.getElementById('tp-title');
  if(tpTitle) tpTitle.textContent = t('thinkEffortTitle');
  _renderThinkState();
  const lblAdv2 = document.getElementById('lbl-advanced');
  if(lblAdv2) lblAdv2.textContent = t('advanced');

  const langSel = document.getElementById('lang-select');
  if(langSel) langSel.value = l;

  renderThemeGrid();

  const sessList = document.getElementById('session-list');
  if(sessList && sessionList.length === 0){
    const noChatsDiv = sessList.querySelector('div[style*="padding:14px"]');
    if(noChatsDiv) noChatsDiv.textContent = t('noChats');
  }

  // Full rebuild so suggestion chips and every welcome string switch at once
  if(!currentSid && document.querySelector('.welcome')) showWelcome();

  document.querySelectorAll('.copy-label').forEach(el => { el.textContent = t('copy'); });
  if(!currentSid) document.getElementById('sess-title').textContent = 'piSynapse';

  // Re-render cached widget items (weather condition label + icon) in the new language
  if(_cachedWeatherRaw !== null) rebuildTickerFromCache();

  // If settings are open, redraw them in the new language immediately
  const sm = document.getElementById('settings-modal');
  if(sm && sm.classList.contains('open')) openSettings();
}

function _thinkBtn(){ return document.getElementById('inline-think-btn'); }
function _thinkSplit(){ return document.getElementById('think-split'); }
function _thinkChev(){ return document.getElementById('think-chev'); }
function _thinkIndex(){ const e = thinkMode ? thinkEffort : lastThinkEffort; return Math.max(0, THINK_LEVELS.findIndex(l => l.effort === e)); }

function _levelName(effort){
  const names = { minimal:'thinkMin', low:'thinkLow', medium:'thinkMed', high:'thinkHigh', xhigh:'thinkMax' };
  return t(names[effort] || 'thinkMed');
}

function _renderThinkState(){
  const idx = _thinkIndex();
  _thinkBtn().classList.toggle('active', thinkMode);
  const split = _thinkSplit();
  if(split){
    split.classList.toggle('active', thinkMode);
    split.classList.remove('lv0','lv1','lv2','lv3','lv4','lv5');
    split.classList.add(thinkMode ? 'lv'+(idx+1) : 'lv0');
  }
  _thinkBtn().title = t('thinkTitle') + ' (' + (thinkMode ? _levelName(thinkEffort) : t('thinkNone')) + ')';
  const chev = _thinkChev();
  if(chev) chev.style.color = thinkMode ? 'var(--accent)' : 'var(--text3)';
  _syncPopover();
}

function toggleThink(){
  if(thinkMode){ lastThinkEffort = thinkEffort; thinkEffort = 'none'; }
  else { thinkEffort = lastThinkEffort; }
  localStorage.setItem('ps_think_effort', thinkEffort);
  thinkMode = thinkEffort !== 'none';
  if(thinkMode) lastThinkEffort = thinkEffort;
  _renderThinkState();
  toast(thinkMode ? t('thinkOn') : t('thinkOff'));
}

function _syncPopover(){
  const pop = document.getElementById('think-popover');
  if(!pop || pop.classList.contains('hidden')) return;
  const idx = _thinkIndex();
  const disp = thinkMode ? thinkEffort : lastThinkEffort;
  const slider = document.getElementById('tp-slider');
  if(slider){
    slider.setAttribute('aria-valuenow', idx);
    slider.setAttribute('aria-valuetext', _levelName(disp));
  }
  const el = document.getElementById('tp-level');
  if(el) el.textContent = _levelName(disp);
  const hint = document.getElementById('tp-hint');
  if(hint) hint.textContent = THINK_LEVELS[idx].hint[lang];
  const thumb = document.getElementById('tp-thumb');
  if(thumb) thumb.style.left = (idx/4*100) + '%';
  const fill = document.getElementById('tp-fill');
  if(fill) fill.style.width = (idx/4*100) + '%';
  const dots = document.getElementById('tp-dots');
  if(dots) dots.querySelectorAll('.tp-dot').forEach((d,i) => d.classList.toggle('on', i === idx));
}

function toggleThinkPopover(e){
  if(!THINK_EFFORT_PICKER) return;
  if(e) e.stopPropagation();
  const pop = document.getElementById('think-popover');
  if(!pop) return;
  const wasOpen = pop.classList.contains('open');
  closeThinkPopover();
  if(!wasOpen){
    pop.classList.remove('hidden');
    requestAnimationFrame(() => {
      _syncPopover();
      pop.classList.add('open');
      const slider = document.getElementById('tp-slider');
      if(slider) slider.focus();
    });
  }
}

function closeThinkPopover(){
  const pop = document.getElementById('think-popover');
  if(!pop) return;
  if(pop.classList.contains('open')){
    pop.classList.remove('open');
    setTimeout(() => pop.classList.add('hidden'), 200);
  } else {
    pop.classList.add('hidden');
  }
}

function setThinkEffort(effort){
  if(!THINK_EFFORTS.includes(effort)) return;
  thinkEffort = effort;
  localStorage.setItem('ps_think_effort', effort);
  thinkMode = true;
  lastThinkEffort = effort;
  _renderThinkState();
  _syncPopover();
}

function _sliderIndexFromEvent(ev){
  const slider = document.getElementById('tp-slider');
  const r = slider.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
  return Math.round(x * 4);
}

function _initThinkPopover(){
  if(!THINK_EFFORT_PICKER){
    const split = _thinkSplit();
    if(split) split.classList.add('no-picker');
    return;
  }
  const slider = document.getElementById('tp-slider');
  const dots = document.getElementById('tp-dots');
  if(!slider || !dots) return;
  let dragging = false;
  THINK_LEVELS.forEach((l, i) => {
    const d = document.createElement('span');
    d.className = 'tp-dot';
    d.style.left = (i/4*100) + '%';
    dots.appendChild(d);
  });
  slider.addEventListener('pointerdown', ev => {
    ev.preventDefault();
    dragging = true;
    slider.setPointerCapture(ev.pointerId);
    setThinkEffort(THINK_LEVELS[_sliderIndexFromEvent(ev)].effort);
  });
  slider.addEventListener('pointermove', ev => {
    if(!dragging) return;
    setThinkEffort(THINK_LEVELS[_sliderIndexFromEvent(ev)].effort);
  });
  ['pointerup','pointercancel'].forEach(evt => {
    slider.addEventListener(evt, () => { dragging = false; });
  });
  slider.addEventListener('keydown', ev => {
    const idx = _thinkIndex();
    if(ev.key === 'ArrowLeft' || ev.key === 'ArrowDown'){ ev.preventDefault(); setThinkEffort(THINK_LEVELS[Math.max(0, idx-1)].effort); }
    else if(ev.key === 'ArrowRight' || ev.key === 'ArrowUp'){ ev.preventDefault(); setThinkEffort(THINK_LEVELS[Math.min(4, idx+1)].effort); }
    else if(ev.key === 'Home'){ ev.preventDefault(); setThinkEffort(THINK_LEVELS[0].effort); }
    else if(ev.key === 'End'){ ev.preventDefault(); setThinkEffort(THINK_LEVELS[4].effort); }
  });
}

document.addEventListener('click', ev => {
  const pop = document.getElementById('think-popover');
  if(pop && pop.classList.contains('open') && !pop.contains(ev.target) && ev.target.id !== 'think-caret'){
    closeThinkPopover();
  }
});
document.addEventListener('keydown', ev => {
  if(ev.key === 'Escape'){
    const pop = document.getElementById('think-popover');
    if(pop && pop.classList.contains('open')) closeThinkPopover();
  }
});

// ── Image Upload ─────────────────────────────────────────────────────────────
let pendingImages = []; // [{name, base64, preview}]
let _pendingStream = null; // sid of the currently streaming response

function handleFiles(files){
  for(const f of files){
    if(!f.type.startsWith('image/')) continue;
    if(pendingImages.length >= 5){ toast('Max 5 images', true); break; }
    const reader = new FileReader();
    reader.onload = e => {
      const dataUrl = e.target.result;
      const base64 = dataUrl.split(',')[1];
      pendingImages.push({name: f.name, base64, preview: dataUrl});
      renderImagePreview();
    };
    reader.readAsDataURL(f);
  }
  document.getElementById('file-input').value = '';
}

function renderImagePreview(){
  const box = document.getElementById('image-preview');
  if(!pendingImages.length){ box.classList.add('hidden'); box.innerHTML=''; return; }
  box.classList.remove('hidden');
  box.innerHTML = pendingImages.map((img,i) =>
    `<div class="preview-item"><img src="${img.preview}" alt="${esc(img.name)}"><button class="preview-remove" onclick="removeImage(${i})">&times;</button></div>`
  ).join('');
}

function removeImage(i){
  pendingImages.splice(i,1);
  renderImagePreview();
}

// Drag & drop
let dragCounter = 0;
document.addEventListener('DOMContentLoaded', () => {
  const overlay = document.getElementById('drag-overlay');
  document.addEventListener('dragenter', e => {
    e.preventDefault(); dragCounter++;
    if(e.dataTransfer.types.includes('Files')) overlay.classList.add('active');
  });
  document.addEventListener('dragleave', e => {
    e.preventDefault(); dragCounter--;
    if(dragCounter <= 0){ dragCounter=0; overlay.classList.remove('active'); }
  });
  document.addEventListener('dragover', e => e.preventDefault());
  document.addEventListener('drop', e => {
    e.preventDefault(); dragCounter=0; overlay.classList.remove('active');
    if(e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  });
  _initThinkPopover();
  const tpTitle = document.getElementById('tp-title');
  if(tpTitle) tpTitle.textContent = t('thinkEffortTitle');
  _renderThinkState();
});

// ── Voice Input ──────────────────────────────────────────────────────────────
// Two local STT engines, switchable from Settings > Speech Engine (STT):
//
// 1. gemma4 (default) — Gemma 4 E2B/E4B native audio via /v1/chat/completions
//    Pros: captures emotion/tone/mood (inferred from transcript content, not voice), no separate model download
//    Cons: slower (~5-15s on Raspberry Pi), less precise transcription
//    How: browser records WebM → ffmpeg converts to WAV 16kHz → Ollama input_audio
//
// 2. whisper — faster-whisper (local Whisper C++ port, tiny model ~75MB)
//    Pros: fast (~1-2s), very accurate transcription, lightweight
//    Cons: no emotion/tone detection, text-only output
//
// Fallback chain: chosen engine → alternate engine → Web Speech API (Google, NOT private)
// All processing stays local. Web Speech API is last resort only.
let voiceState = 'idle'; // idle | recording | transcribing
let mediaRecorder = null;
let audioChunks = [];
let voiceStream = null;
let voiceTimer = null;
let voiceCountdown = null;
const MAX_VOICE_SECONDS = 30;

function toggleVoice(){
  if(voiceState === 'recording') stopVoice();
  else if(voiceState === 'idle') startVoice();
}

function startVoice(){
  if(voiceState !== 'idle') return;

  if(!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1'){
    toast(t('micHttps'), true);
    return;
  }

  if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
    toast(t('micNoEngine'), true);
    return;
  }

  navigator.mediaDevices.getUserMedia({audio: true}).then(stream => {
    if(voiceState !== 'idle') { stream.getTracks().forEach(t => t.stop()); return; }
    voiceStream = stream;
    audioChunks = [];

    const mimeTypes = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',
      'audio/mp4;codecs=mp4a.40.2',
      'audio/aac',
    ];
    let selectedMime = '';
    for(const mt of mimeTypes){
      if(MediaRecorder.isTypeSupported(mt)){ selectedMime = mt; break; }
    }
    if(!selectedMime){
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if(SR){ startWebSpeechFallback(SR); return; }
      toast(t('micNoEngine'), true);
      stream.getTracks().forEach(t => t.stop());
      return;
    }

    try {
      mediaRecorder = new MediaRecorder(stream, {mimeType: selectedMime, audioBitsPerSecond: 128000});
    } catch(e){
      console.warn('MediaRecorder creation failed:', e);
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if(SR){ startWebSpeechFallback(SR); return; }
      toast(t('micNoEngine'), true);
      stream.getTracks().forEach(t => t.stop());
      return;
    }

    mediaRecorder.ondataavailable = e => { if(e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onerror = e => {
      console.warn('MediaRecorder error:', e.error);
      toast(t('transcribeErr'), true);
      resetVoice();
    };
    mediaRecorder.onstop = () => processRecording(selectedMime);
    voiceState = 'recording';
    document.getElementById('mic-btn').classList.add('mic-recording');
    haptic(50);
    mediaRecorder.start(1000);
    startVoiceTimer();
  }).catch(err => {
    console.warn('getUserMedia failed:', err);
    voiceState = 'idle';
    if(err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError'){
      if(location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1'){
        toast(t('micHttps'), true);
      } else {
        toast(t('micDenied'), true);
      }
    } else {
      toast(t('transcribeErr'), true);
    }
  });
}

async function processRecording(mimeUsed){
  voiceStream.getTracks().forEach(t => t.stop());
  voiceStream = null;
  const blob = new Blob(audioChunks, {type: mimeUsed || 'audio/webm'});
  audioChunks = [];
  if(blob.size < 500){ resetVoice(); return; }

  voiceState = 'transcribing';
  showTranscribing();
  const el = document.getElementById('msg-input');
  const engine = config.stt_engine || 'whisper';

  const isWebM = (mimeUsed || '').includes('webm');
  const audioFile = isWebM ? 'recording.webm' : 'recording.mp4';
  const engines = engine === 'whisper'
    ? (isWebM ? ['/chat/transcribe', '/chat/transcribe-gemma4'] : ['/chat/transcribe-gemma4', '/chat/transcribe'])
    : (isWebM ? ['/chat/transcribe-gemma4', '/chat/transcribe'] : ['/chat/transcribe', '/chat/transcribe-gemma4']);

  const engineNames = {'/chat/transcribe': t('micTryingWhisper'), '/chat/transcribe-gemma4': t('micTryingGemma4')};

  for(const endpoint of engines){
    const label = engineNames[endpoint] || endpoint;
    document.getElementById('mic-timer').textContent = label;
    try {
      const fd = new FormData();
      fd.append('audio', blob, audioFile);
      const headers = {};
      const key = getApiKey();
      if(key) headers['X-API-Key'] = key;
      let url = API + endpoint;
      if(endpoint === '/chat/transcribe' || endpoint === '/chat/transcribe-gemma4') url += '?lang=' + encodeURIComponent(lang);
      const resp = await fetch(url, {method: 'POST', body: fd, headers});
      if(!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      if(!data.text || !data.text.trim()){
        console.warn(endpoint + ': empty transcription');
        continue;
      }
      el.value = data.text;
      el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px';
      resetVoice();
      // Auto-send if voice auto-send is enabled
      const autoSend = config.auto_send_on_voice === 'on';
      if(autoSend){
        lastInputWasVoice = true;
        setTimeout(() => sendMsg(), 50);
      }
      return;
    } catch(e) {
      console.warn(endpoint + ' failed:', e);
    }
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if(SpeechRecognition){
    if(!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1'){
      toast(t('micHttps'), true);
      resetVoice();
      return;
    }
    document.getElementById('mic-timer').textContent = t('micTryingBrowser');
    startWebSpeechFallback(SpeechRecognition);
    return;
  }

  toast(t('transcribeErr'), true);
  resetVoice();
}

function showTranscribing(){
  const micBtn = document.getElementById('mic-btn');
  micBtn.classList.remove('mic-recording');
  micBtn.classList.add('mic-starting');
  const timer = document.getElementById('mic-timer');
  timer.style.display = 'block';
  timer.textContent = '...';
}

function startWebSpeechFallback(SpeechRecognition){
  const speechRec = new SpeechRecognition();
  speechRec.lang = lang === 'tr' ? 'tr-TR' : lang === 'en' ? 'en-US' : lang;
  speechRec.continuous = false;
  speechRec.interimResults = true;
  const el = document.getElementById('msg-input');
  let finalTranscript = el.value ? el.value + ' ' : '';

  speechRec.onresult = e => {
    let interim = '';
    for(let i = e.resultIndex; i < e.results.length; i++){
      const transcript = e.results[i][0].transcript;
      if(e.results[i].isFinal) finalTranscript += transcript; else interim = transcript;
    }
    el.value = finalTranscript + interim;
    el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px';
  };

  speechRec.onend = () => resetVoice();
  speechRec.onerror = e => {
    console.warn('Web Speech API error:', e.error);
    if(e.error === 'not-allowed') toast(t('micDenied'), true);
    else toast(t('transcribeErr'), true);
    resetVoice();
  };

  voiceState = 'recording';
  document.getElementById('mic-btn').classList.add('mic-recording');
  speechRec.start();
  startVoiceTimer();
}

function stopVoice(){
  if(voiceState !== 'recording') return;
  clearInterval(voiceTimer);
  clearInterval(voiceCountdown);
  if(mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
}

function resetVoice(){
  voiceState = 'idle';
  clearInterval(voiceTimer);
  clearInterval(voiceCountdown);
  const micBtn = document.getElementById('mic-btn');
  micBtn.classList.remove('mic-recording', 'mic-starting');
  const timer = document.getElementById('mic-timer');
  timer.style.display = 'none';
  timer.textContent = '';
  if(voiceStream){ voiceStream.getTracks().forEach(t => t.stop()); voiceStream = null; }
  mediaRecorder = null; audioChunks = [];
}

function startVoiceTimer(){
  let remaining = MAX_VOICE_SECONDS;
  updateTimerDisplay(remaining);
  voiceTimer = setInterval(() => {
    remaining--;
    if(remaining <= 0){ stopVoice(); return; }
    updateTimerDisplay(remaining);
  }, 1000);
}

function updateTimerDisplay(sec){
  const timer = document.getElementById('mic-timer');
  timer.textContent = sec;
}

function haptic(ms){
  if(navigator.vibrate) navigator.vibrate(ms);
}

// ── TTS (Text-to-Speech) ────────────────────────────────────────────────────
// Two engines, switchable from Settings > Speech Engine (TTS):
//
// 1. piper (default) — Piper TTS local .onnx models
//    Pros: consistent quality, fully offline, privacy-safe
//    Cons: limited voice selection, requires model download (~50MB each)
//
// 2. browser — Web Speech API (speechSynthesis)
//    Pros: many voices, no model download, fast
//    Cons: sends text to Google/Apple servers (privacy risk), quality varies

let ttsAudio = null;
let ttsBtn = null;
let ttsAbort = null;

async function toggleTTS(text, btn){
  // Stop if already playing
  if(ttsBtn === btn){
    stopTTS();
    return;
  }
  stopTTS();
  ttsBtn = btn;
  // The engine (Piper) takes a beat to produce the audio — light the button
  // immediately so the wait is visible, then hand over to the playing state.
  btn.classList.add('tts-loading');
  const engine = (_settingsData.TTS_ENGINE && _settingsData.TTS_ENGINE.value) || 'piper';

  if(engine === 'browser'){
    playBrowserTTS(text, btn);
  } else {
    await playPiperTTS(text, btn);
  }
}

function playBrowserTTS(text, btn){
  if(!('speechSynthesis' in window)){ toast(t('ttsErr'), true); resetTTS(); return; }
  const utt = new SpeechSynthesisUtterance(stripMarkdown(text).slice(0, 2000));
  utt.lang = lang === 'tr' ? 'tr-TR' : lang === 'en' ? 'en-US' : lang;
  utt.rate = 1;
  const voices = speechSynthesis.getVoices();
  const match = voices.find(v => v.lang.startsWith(lang)) || voices.find(v => v.lang.startsWith('en'));
  if(match) utt.voice = match;
  utt.onstart = () => { if(ttsBtn){ ttsBtn.classList.remove('tts-loading'); ttsBtn.classList.add('tts-playing'); } };
  utt.onend = () => { if(ttsBtn) ttsBtn.classList.remove('tts-playing'); ttsBtn = null; };
  utt.onerror = () => { toast(t('ttsErr'), true); resetTTS(); };
  speechSynthesis.speak(utt);
}

async function playPiperTTS(text, btn){
  const ac = new AbortController();
  ttsAbort = ac;
  try {
    const voice = (_settingsData.TTS_VOICE && _settingsData.TTS_VOICE.value) || '';
    const headers = {'Content-Type':'application/json'};
    const key = getApiKey();
    if(key) headers['X-API-Key'] = key;
    const r = await fetch(API + '/chat/tts', {method:'POST', headers,
      body: JSON.stringify({text: text.slice(0, 2000), voice}), signal: ac.signal});
if(r.status === 503) throw new Error('HTTP 503');
  if(!r.ok) throw new Error('HTTP '+r.status);
    const blob = await r.blob();
    if(ac.signal.aborted) return;
    ttsAudio = new Audio(URL.createObjectURL(blob));
    ttsAudio.onplay = () => { if(ttsBtn){ ttsBtn.classList.remove('tts-loading'); ttsBtn.classList.add('tts-playing'); } };
    ttsAudio.onended = () => { if(ttsBtn) ttsBtn.classList.remove('tts-playing'); ttsBtn = null; };
    ttsAudio.onerror = () => { toast(t('ttsErr'), true); resetTTS(); };
    ttsAudio.play().catch(() => {
      if(ac.signal.aborted){ resetTTS(); return; } // cancelled mid-wait: silent
      toast(t('ttsErr'), true); resetTTS();
    });
  } catch(e) {
    if(e && e.name === 'AbortError'){ resetTTS(); return; } // intentional second-click cancel
    toast(t('ttsErr'), true);
    resetTTS();
  }
}

function stopTTS(){
  // Cancel an in-flight Piper request (second click = abort, no orphan audio)
  if(ttsAbort){ ttsAbort.abort(); ttsAbort = null; }
  // Stop Piper (Audio element)
  if(ttsAudio && ttsAudio.src){
    ttsAudio.pause(); ttsAudio.currentTime = 0; ttsAudio = null;
  }
  // Stop browser TTS
  if('speechSynthesis' in window) speechSynthesis.cancel();
  if(ttsBtn) ttsBtn.classList.remove('tts-playing');
  if(ttsBtn) ttsBtn.classList.remove('tts-loading');
  ttsBtn = null;
}

function resetTTS(){
  stopTTS();
}

// ── API Communication ───────────────────────────────────────────────────────────
const API = window.location.origin;

function getApiKey(){
  const sd = (typeof _settingsData !== 'undefined' && _settingsData) ? _settingsData : window._settingsData;
  const serverKey = (sd && sd.SERVER_API_KEY) ? (sd.SERVER_API_KEY.value || '') : '';
  return localStorage.getItem('ps_api_key') || serverKey || '';
}
function setApiKey(k){ localStorage.setItem('ps_api_key', k); }

// ── Yerel (Capacitor) köprüsü ─────────────────────────────────────────────
// Web'de PiSynapse yokken _NATIVE null kalır; tüm bu olay akışı devre dışıdır.
const _NATIVE = (()=>{ try{ if('PiSynapse' in window) return window.PiSynapse; if(typeof window.Capacitor!=='undefined' && window.Capacitor.Plugins && window.Capacitor.Plugins.PiSynapse) return window.Capacitor.Plugins.PiSynapse; return null; }catch(e){ return null; } })();
// Browser (MASTER) view overrides: the web root is the server console, so the
// onboarding/welcome copy must describe the server, not the phone.
if(!_NATIVE){
  STRINGS.tr.welcomeSub = 'Kendi sunucun. Senin verilerin.\nTüm veriler Pi\'nde kalır.';
  STRINGS.tr.obS1S = 'piSynapse kendi sunucunda çalışır — sohbetlerin, hafızan ve takvimin Pi\'nde kalır.';
  STRINGS.tr.obTip4 = 'Ayarlar: tema, dil, font';
  STRINGS.en.welcomeSub = 'Own server. Your data.\nEverything stays on your Pi.';
  STRINGS.en.obS1S = 'piSynapse runs on your own server — chats, memory and calendar stay on your Pi.';
  STRINGS.en.obTip4 = 'Settings: theme, language, font';
  const _s6 = STRINGS.tr.obS6S;
  if(typeof _s6 === 'string' && _s6.indexOf('Bu cihazı') === 0){
    STRINGS.tr.obS6S = 'Bu sunucuya bağlan (oturum aç). Boş bırakıp atlayabilirsin; sonradan Ayarlar · Sunucu üzerinden düzenleyebilirsin.';
  }
  const _s6e = STRINGS.en.obS6S;
  if(typeof _s6e === 'string' && _s6e.toLowerCase().indexOf('connect this device') === 0){
    STRINGS.en.obS6S = 'Connect to this server (log in). You can skip and edit it later from Settings · Server.';
  }
  const _s6h = STRINGS.tr.obS6Hint;
  if(typeof _s6h === 'string' && _s6h.indexOf('Tarayıcıda') === 0){
    STRINGS.tr.obS6Hint = 'API anahtarı sunucunun .env dosyasındaki API_KEY değeridir. Sunucu adresi açtığın adresle zaten doldurulur.';
  }
  const _s6he = STRINGS.en.obS6Hint;
  if(typeof _s6he === 'string' && _s6he.indexOf('In browser mode') === 0){
    STRINGS.en.obS6Hint = 'The API key is the API_KEY value in your server\'s .env file. The server URL is pre-filled with the address you opened.';
  }
}
let _nativeHistory = [];
let _nativeSessions = [];
let _nativeSessionHistory = {};

async function _nativeApiRoute(method, path, body){
  const P = ()=>_NATIVE;
  if(method === 'GET' && path === '/config'){
    const s = await P().configGet();
    const v = (k)=>{ const o=s[k]; return o?o.value:''; };
    const uname = (v('ASSISTANT_USER')||'').trim() || (v('SERVER_USER')||'').trim() || 'default';
    return { username:uname, default_city:v('DEFAULT_CITY'), model:v('LLM_MODEL'),
      stt_engine:'whisper', tts_engine:'piper', auto_send_on_voice:'off',
      auto_tts_on_voice:v('TTS_AUTO_REPLY')==='on'?'on':'off', llm_title_enrichment:'off',
      has_llm:true, native:true };
  }
  if(method === 'GET' && path === '/config/settings'){
    const s = await P().configGet();
    const out = {};
    Object.keys(s).forEach(k=>{ out[k] = s[k]; });
    return out;
  }
  if(method === 'PATCH' && path === '/config/settings'){
    if(body && body.values) await P().configSet({ values: body.values });
    return { ok:true };
  }
  if(method === 'GET' && path === '/widget/weather'){
    const w = await P().invokeTool({ group:'weather', name:'get_weather', params:{} });
    if(w.ok === false || !w.temp_c) throw new Error('weather-unavailable');
    return { summary:w.summary, kind:w.kind, temp_c:w.temp_c, condition:w.condition, wmo_code:w.wmo_code };
  }
  if(method === 'GET' && path === '/health'){
    const ms = await P().modelStatus();
    return { ok:true, llm: ms.available?'yedek':'yok', model_file: ms.model_file||'' };
  }
  if(method === 'GET' && path === '/chat/sessions'){
    if(_serverMode === 'only-server'){
      try{ return await _NATIVE.chatSyncSessions(); }catch(e){}
    }
    return { sessions: _nativeSessions };
  }
  if(method === 'GET' && path.startsWith('/chat/history')){
    const q = new URLSearchParams((path.split('?')[1]) || '');
    const sid = q.get('session_id') || currentSid || '';
    if(_serverMode === 'only-server' && sid){
      const src = await _NATIVE.chatHistory({ session_id: sid });
      if(src && src.ok) return { session_id: sid, messages: src.messages||[] };
    }
    const msgs = (sid && _nativeSessionHistory[sid]) ? _nativeSessionHistory[sid] : [];
    return { session_id: sid, messages: msgs };
  }
  if(method === 'GET' && path.startsWith('/chat/search')){
    return { results: [], sessions: [] };
  }
  if(method === 'GET' && path.split('?')[0] === '/chat/memories'){
    const m = await P().listMemory();
    return m;
  }
  if(method === 'DELETE' && path.startsWith('/chat/history')){
    const q = new URLSearchParams((path.split('?')[1]) || '');
    const sid = q.get('session_id') || '';
    if(sid){
      if(_serverMode === 'only-server'){ try{ await _NATIVE.deleteSession({ session_id: sid }); }catch(e){} }
      delete _nativeSessionHistory[sid];
      _nativeSessions = (_nativeSessions||[]).filter(s=>s.session_id!==sid);
      _nativeHistory = (_nativeHistory||[]).slice(-40);
    }
    _nativeChatSave(true);
    return { ok:true };
  }
  if(method === 'DELETE' && path.startsWith('/chat/memories')){
    const q = new URLSearchParams((path.split('?')[1]) || '');
    const res = await P().deleteMemory({ id: q.get('id') || '' });
    return { status: res.status, message: res.message };
  }
  if(method === 'GET' && path === '/tools/groups'){
    return { groups: [] };
  }
  if(method === 'POST' && path === '/chat/execute' && body && body.tool){
    const res = await P().invokeTool({ group: body.tool, name: body.tool, params: body.params || {} });
    if(res.ok === false) throw new Error(res.error || 'tool-failed');
    const text = res.reply || res.result || res.note || '';
    return { reply: text };
  }
  return undefined;
}

// chatStream'ı SPA'nın beklediği SSE biçimine dönüştürür: plugin olaylarını
// `data: {...}` satırlarına çeviren {ok, body:{getReader}} nesnesi döndürür.
async function _nativeSSEResponse(payload){
  const queue=[], enc=new TextEncoder();
  let waiting=null, finished=false, _acc='', lh=null;
  const sid = payload.session_id || '';
  const pushEvent=(d)=>{
    if(finished) return;
    queue.push(d);
    if(d.done || d.error || d.confirm) finished=true;
    if(waiting){ const w=waiting; waiting=null; w(); }
  };
  const onEvt=(evt)=>{
    const d=(evt && evt.data && typeof evt.data==='object') ? evt.data : evt;
    if(!d) return;
    if(d.token) _acc += d.token;
    if(d.done || d.error){ _nativeHistory.push({role:'assistant', content:_acc}); _nativeSessionPush(sid,{role:'assistant', content:_acc}); _nativeChatSave(true); }
    pushEvent(d);
  };
  _nativeHistory.push({role:'user', content: payload.message||''});
  _nativeSessionPush(sid,{role:'user', content: payload.message||''});
  if(payload.session_id && !_nativeSessions.some(s=>s.session_id===payload.session_id)){
    _nativeSessions.push({session_id:payload.session_id, name:'', last_active:new Date().toISOString(), message_count:0});
  }
  lh = await _NATIVE.addListener('chatEvent', onEvt);
  _NATIVE.chatStream({ payload }).catch(err=>{
    pushEvent({error: (err && err.message) || String(err) || 'native-stream-failed'});
  });
  return {
    ok:true, status:200,
    body: { getReader(){ return {
      async read(){
        if(queue.length===0){
          if(finished) return {done:true, value:undefined};
          await new Promise(res=>{ waiting=res; });
        }
        const d=queue.shift();
        return {done:false, value: enc.encode('data: '+JSON.stringify(d)+'\n')};
      }
    }; } }
  };
}

function _nativeSessionPush(sid, m){
  if(!sid) return;
  _nativeSessionHistory[sid] = _nativeSessionHistory[sid] || [];
  _nativeSessionHistory[sid].push(m);
}

let _nativeSaveTimer = null;
let _nativePushTimer = null;
function _nativeChatSave(immediate){
  if(!_NATIVE) return;
  if(_nativeSaveTimer) clearTimeout(_nativeSaveTimer);
  const doSave = ()=>{
    _nativeSaveTimer = null;
    try{
      // Bound memory/file growth: flat context keeps a window, per-session keeps recent turns.
      const flat = (_nativeHistory||[]).length > 80 ? _nativeHistory.slice(-80) : _nativeHistory;
      const sess = {};
      for(const k of Object.keys(_nativeSessionHistory||{})){
        const arr = _nativeSessionHistory[k]||[];
        sess[k] = arr.length > 40 ? arr.slice(-40) : arr;
      }
      const payload={sessions:_nativeSessions||[], history:flat, sessionHistory:sess};
      _NATIVE.chatHistorySave({ data: JSON.stringify(payload) }).catch(()=>{});
      // Mirror local chats to the paired server (only-server / SYNC_ALWAYS).
      // Debounced so a streaming burst produces one batched import.
      if(_nativePushTimer) clearTimeout(_nativePushTimer);
      _nativePushTimer = setTimeout(()=>{
        _nativePushTimer = null;
        _NATIVE.chatPush({ data: JSON.stringify({sessions:_nativeSessions||[], sessionHistory:sess}) })
          .catch(()=>{});
      }, 1500);
    }catch(e){}
  };
  if(immediate) doSave();
  else _nativeSaveTimer = setTimeout(doSave, 700);
}

async function _nativeChatRestore(){
  if(!_NATIVE) return;
  try{
    const r = await _NATIVE.chatHistoryLoad();
    if(r && Array.isArray(r.history)) _nativeHistory = r.history;
    if(r && Array.isArray(r.sessions)) _nativeSessions = r.sessions;
    if(r && r.sessionHistory && typeof r.sessionHistory === 'object') _nativeSessionHistory = r.sessionHistory;
  }catch(e){}
  // only-server: pull the full chat state from the server so a cold phone
  // shows the same sidebar + conversations as the server dashboard.
  if(_NATIVE && _settingsData && _settingsData.SYNC_MODE && _settingsData.SYNC_MODE.value==='only-server'){
    try{
      const pr = await _NATIVE.chatPull();
      if(pr && pr.ok){
        if(Array.isArray(pr.sessions) && pr.sessions.length){
          // Server sessions already carry {session_id, name, last_active, message_count}
          // — exactly what renderSessions()/sessName() expect.
          _nativeSessions = pr.sessions;
        }
        if(pr.sessionHistory && typeof pr.sessionHistory==='object'){
          _nativeSessionHistory = pr.sessionHistory;
        }
        // Persist the pulled state so it survives an app restart even offline.
        // Deliberately NOT _nativeChatSave(): that would re-arm the push timer
        // and re-import server mesgages under a phone: key, creating duplicates.
        try{
          _NATIVE.chatHistorySave({ data: JSON.stringify({sessions:_nativeSessions||[], history:_nativeHistory||[], sessionHistory:_nativeSessionHistory||{}}) }).catch(()=>{});
        }catch(e){}
      }
    }catch(e){}
    // MASTER→SLAVE: existing server session on restart — pull portable settings.
    try{ await _serverSettingsPull(); }catch(e){}
  }
}

function _nativeSystem(){
  return 'Sen PiSynapse asistanısın; Türkçe yanıt ver, kısa ve doğrudan konuş, markdown kullanabilirsin. '+
    'Bu telefon uygulaması tamamen yerel çalışır. Araçlar: get_datetime (saat/tarih), get_weather (Ayarlardaki şehir), '+
    'list_notes/read_note/create_note/update_note/delete_note (Nextcloud), save_memory, create_task/list_tasks/complete_task, '+
    'send_email (e-posta uygulamasını açar), create_calendar_event (takvim uygulamasını açar). '+
    'Sunucuya, önceki oturumlara ve internete kalıcı erişimin yok; yalnız bu konuşmadaki bağlamı kullan. '+
    'Kullanıcı geçmiş isterse, bunun yerel kısıtlı bir uygulama olduğunu söyle.';
}

// MASTER→SLAVE: pull portable server settings into the phone on successful
// server login. Only security-safe, portable keys are written to the local
// ConfigStore (NEXTCLOUD_* connection, personal identity) — never the server's
// LLM/model or infrastructure settings.
const _PORTABLE_KEYS = ['NEXTCLOUD_URL','NEXTCLOUD_USER','NEXTCLOUD_PASSWORD','ASSISTANT_USER','DEFAULT_CITY'];
async function _serverSettingsPull(){
  if(!_NATIVE) return;
  try{
    const pr = await _NATIVE.pullServerSettings();
    if(!pr || !pr.ok || !pr.settings) return;
    const values = {};
    for(const k of _PORTABLE_KEYS){
      const entry = pr.settings[k];
      if(entry && entry.value !== undefined && entry.value !== '') values[k] = entry.value;
    }
    if(Object.keys(values).length){
      // Save directly to local ConfigStore (not the global _settingsData which
      // is native-backed anyway). Non-destructive merge.
      try{ await _NATIVE.configSet({ values }); }catch(e){}
      // Re-read local config so the UI reflects synced identity/Nextcloud.
      try{
        const s = await _NATIVE.configGet();
        if(s) Object.assign(_settingsData, s);
      }catch(e){}
      try{ if(window._beacon) window._beacon({t:'settings-pull', n:Object.keys(values).length}); }catch(e){}
    }
  }catch(e){
    // Silent: server unreachable right after login is acceptable; next restore retries.
  }
}

async function api(method, path, body){
  if(_NATIVE){
    try{
      const r = await _nativeApiRoute(method, path, body);
      if(r !== undefined) return r;
    }catch(e){
      // Swallow offline-style failures; network routes below apply on web.
      if(path.startsWith('/chat') || path.startsWith('/config')) throw e;
    }
  }
  const headers = {'Content-Type':'application/json'};
  const key = getApiKey();
  if(key) headers['X-API-Key'] = key;
  const opts = {method, headers};
  if(body) opts.body = JSON.stringify(body);
  const r = await fetch(API+path, opts);
  if(r.status === 401){
    if(!key && !window._authPrompted){
      window._authPrompted = true;
      const newKey = prompt(t('apiKeyPrompt'));
      if(newKey){
        setApiKey(newKey);
        headers['X-API-Key'] = newKey;
        const r2 = await fetch(API+path, {method, headers, body: opts.body});
        if(r2.ok) return r2.json();
      }
    }
    if(key) setApiKey('');
    throw new Error('HTTP 401');
  }
  if(!r.ok) throw new Error('HTTP '+r.status);
  return r.json();
}

let config = {username:'', default_city:'', model:'', stt_engine:'whisper', tts_engine:'piper', auto_send_on_voice:'off', auto_tts_on_voice:'off'};
let lastInputWasVoice = false;

document.addEventListener('DOMContentLoaded', async ()=>{
  if(window._beacon) window._beacon({t:'init', step:'start'});
  applyTheme(theme); applyGlass(glass); applyMinimal(minimal); applyAmoled(amoled); applyFont(fontMode); applyLang(lang); enhanceAllSelects(); setupInput(); setupMobileKeyboard(); setupHoldToRecord();
  if(window._beacon) window._beacon({t:'init', step:'prep-done'});
  // Check if API key is needed
  try {
    config = await api('GET','/config');
  } catch(e){
    if(e.message === 'HTTP 503'){
      // Server is fail-closed but has no API_KEY configured (.env).
      if(!window._misconfWarned){
        window._misconfWarned = true;
        toast(t('serverMisconf'), true);
      }
      if(window._beacon) window._beacon({t:'init', step:'config-503'});
    }
    if(e.message === 'HTTP 401'){
      // API key needed — prompt handled inside api()
      try { config = await api('GET','/config'); } catch {}
    }
  }
  if(window._beacon) window._beacon({t:'init', step:'config-done'});
  // Preload settings so TTS/STT engines work without opening Settings panel
  try {
    const s = await api('GET','/config/settings');
    if(s) Object.assign(_settingsData, s);
    _serverMode = (s && s.SYNC_MODE) ? s.SYNC_MODE.value : '';
    // Adopt the instance's assistant language unless the user picked one.
    if(!localStorage.getItem('ps_lang')){
      const srv = String((_settingsData.UI_LANGUAGE||{}).value||'').toLowerCase();
      if((srv==='tr'||srv==='en') && srv!==lang) applyLang(srv);
    }
  } catch {}
  await _nativeChatRestore();
  // Auto-sync: if the server is configured and SYNC_ALWAYS is on, push+merge
  // DB-backed entities (tasks, memory) once at startup and after settings save.
  _autoSync=async()=>{
    try{
      const st=await _NATIVE.serverStatus();
      const always = (typeof _settingsData!=='undefined' && _settingsData && _settingsData.SYNC_ALWAYS) ? _settingsData.SYNC_ALWAYS.value : '';
      if(st && st.configured && always==='on' && !_syncing){
        _syncing=true;
        try{ await _NATIVE.syncNow(); }finally{ _syncing=false; }
      }
    }catch(e){}
  };
  if(_NATIVE && !_syncing) setTimeout(_autoSync, 4000);
  // Native: once-per-install runtime permission pass (calendar/mic/location).
  // Android shows its own dialog; this only triggers it ONCE via localStorage.
  // On a clean first run the onboarding wizard (step 2) handles permissions instead.
  if(_NATIVE && localStorage.getItem('ps_onboarded')){
    try{
      const st = await _NATIVE.permissionStatus();
      const want = ['calendar','microphone','location'].filter(k=>!(st&&st[k]));
      if(want.length && !localStorage.getItem('ps_perm_asked')){
        localStorage.setItem('ps_perm_asked','1');
        for(const k of want){ try{ await _NATIVE.requestPermission({kind:k}); }catch(e){} }
      }
    }catch(e){}
  }
  startOnboarding();
  await loadSessions(); showWelcome(); startTicker(); startHealthPoll();
  refreshServerStatus();
  if(window._beacon) window._beacon({t:'init', step:'all-done'});
});

function setupInput(){
  const el=document.getElementById('msg-input');
  el.addEventListener('keydown', e=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); sendMsg(); } });
  let _inputRaf=null;
  el.addEventListener('input', ()=>{
    if(_inputRaf) cancelAnimationFrame(_inputRaf);
    _inputRaf=requestAnimationFrame(()=>{ el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,200)+'px'; });
  });
}

function setupMobileKeyboard(){
  if(!('visualViewport' in window)) return;
  const vv=window.visualViewport, ia=document.getElementById('input-area');
  const adjust=()=>{
    const kb=window.innerHeight-vv.height-vv.offsetTop;
    ia.style.bottom=(kb>20 ? kb+10 : 20)+'px';
    if(kb>20) scrollEnd(true);
  };
  vv.addEventListener('resize', adjust); vv.addEventListener('scroll', adjust);
}

// ── Chat History & Loading ──────────────────────────────────────────────────────
async function loadSessions(animate=true){
  try{
    const d=await api('GET','/chat/sessions'); sessionList=d.sessions||[];
    renderSessions(sessionList, animate);
  }
  catch(e){
    if(e.message==='HTTP 401'){ window._authPrompted=false; renderAuthNeeded(); }
    // A transient refresh failure must not blank an already-populated sidebar:
    // wiping to "No chats yet" on a mid-stream hiccup is the classic flicker.
    else if(!sessionList.length) renderSessions([], animate);
  }
}

// Topbar sunucu durum göstergesi: only-server=yeşil (online), only-phone=amber (yerel),
  // bağlantı yok/offline=boş (gizli). Tıklayınca durum detayını toast ile gösterir.
  async function refreshServerStatus(){
    const el=document.getElementById('srv-status');
    if(!el) return;
    const mode = _serverMode || (_settingsData.SYNC_MODE && _settingsData.SYNC_MODE.value) || '';
    if(!_NATIVE || mode===''){
      el.classList.add('hidden');
      return;
    }
    el.classList.remove('hidden');
    if(mode==='only-server'){
      try{
        const st=await _NATIVE.serverStatus();
        el.classList.toggle('online', !!st && st.configured);
        el.classList.remove('local','offline');
        if(!st || !st.configured){ el.classList.add('offline'); if(!el.classList.contains('offline')) el.textContent=''; }
      }catch(e){
        el.classList.add('offline'); el.classList.remove('online','local');
      }
    } else {
      el.classList.add('local'); el.classList.remove('online','offline');
    }
  }
  function toggleServerStatus(){
    if(!_NATIVE) return;
    _NATIVE.serverStatus().then(st=>{
      const mode=_serverMode||'';
      if(mode==='only-server'){
        toast((st&&st.configured) ? ('Sunucu: '+(st.server_url||'')+' — bağlı') : 'Sunucu yapılandırılmadı');
      } else {
        toast('Yerel mod (model cihazda çalışıyor)' + ((st&&st.configured)?' · Sunucu hazır':''));
      }
    }).catch(()=>toast(t('connErr'), true));
  }

function renderAuthNeeded(){
  const el=document.getElementById('session-list');
  if(!el) return;
  el.innerHTML=`<div style="padding:14px 16px 8px;font-size:13px;color:var(--text3)">${t('authNeeded')}</div>
    <button class="sess-auth-btn" onclick="reenterKey()">${t('authEnter')}</button>`;
}

function reenterKey(){
  const k=prompt(t('apiKeyPrompt'));
  if(k){ setApiKey(k); loadSessions(); }
}

function sessName(s){ return s.name || (t('chatPrefix')+' '+s.session_id.slice(-6)); }
function generateRakeTitleJS(text){
  const clean=text.trim();
  if(!clean) return "Yeni Sohbet";
  const words=clean.split(/\s+/);
  let first4=words.slice(0,4).join(' ');
  if(first4.length>40) first4=first4.slice(0,40).split(' ').slice(0,-1).join(' ')+'...';
  return first4;
}

function renderSessions(list, animate=true){
  const el=document.getElementById('session-list');
  if(!el) return;
  el.classList.toggle('no-anim', !animate);
  if(!list.length){ el.innerHTML=`<div style="padding:14px 16px;font-size:13px;color:var(--text4)">${t('noChats')}</div>`; return; }
  // Silent refreshes patch rows in place — reuse live nodes, no rebuild → no reflow / scroll jump
  if(!animate && el.querySelector('.sess-item') && patchSessionList(el, list)) return;
  const sc=el.scrollTop;
  el.innerHTML=list.map(s=>{
    const name=sessName(s), tm=relTime(s.last_active), act=s.session_id===currentSid?' active':'', sid=esc(s.session_id);
    const rawSnippet=s._snippet||s.snippet||"";
    const snippetHtml=rawSnippet?`<div class="sess-snippet">${esc(rawSnippet).replace(/&lt;b&gt;/g,'<b>').replace(/&lt;\/b&gt;/g,'</b>')}</div>`:"";
    return `<div class="sess-item${act}" data-sid="${sid}">
      <div class="sess-name" aria-label="${esc(name)}">${esc(name)}</div>
      <div class="sess-time">${tm}</div>
      ${snippetHtml}
      <button class="sess-del" data-sid="${sid}" aria-label="${t('del')}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
      </button></div>`;
  }).join('');
  // Preserve the user's scroll offset across a rebuild so the list doesn't look like it vanished
  el.scrollTop=sc;
  // Event delegation: single listener for all session items (400→1)
  if(!el._hasDelegation){
    el.addEventListener('click', (e)=>{
      const delBtn=e.target.closest('.sess-del');
      if(delBtn){ e.stopPropagation(); delBtn.closest('.sess-item')?.classList.remove('long-press'); triggerDelSession(delBtn.dataset.sid); return; }
      const item=e.target.closest('.sess-item');
      if(!item) return;
      if(item.classList.contains('long-press')){ item.classList.remove('long-press'); return; }
      document.querySelectorAll('.sess-item.long-press').forEach(el=> el.classList.remove('long-press'));
      loadSession(item.dataset.sid);
    });
    const pressMap=new WeakMap();
    el.addEventListener('touchstart', (e)=>{
      const item=e.target.closest('.sess-item');
      if(!item) return;
      clearTimeout(pressMap.get(item));
      const t=setTimeout(()=>{
        document.querySelectorAll('.sess-item.long-press').forEach(el=>{ if(el!==item) el.classList.remove('long-press'); });
        item.classList.add('long-press');
      }, 350);
      pressMap.set(item,t);
    }, {passive:true});
    el.addEventListener('touchend', (e)=>{ const it=e.target.closest('.sess-item'); if(it) clearTimeout(pressMap.get(it)); });
    el.addEventListener('touchmove', (e)=>{ const it=e.target.closest('.sess-item'); if(it) clearTimeout(pressMap.get(it)); });
    el.addEventListener('touchcancel', (e)=>{ const it=e.target.closest('.sess-item'); if(it) clearTimeout(pressMap.get(it)); });
    el._hasDelegation=true;
  }
  // Tap outside list closes long-press
  document.getElementById('session-list')?.addEventListener('click', (e)=>{
    if(!e.target.closest('.sess-item')) document.querySelectorAll('.sess-item.long-press').forEach(el=> el.classList.remove('long-press'));
  });
  document.addEventListener('click', (e)=>{
    if(!e.target.closest('.sess-item') && !e.target.closest('#session-list')) document.querySelectorAll('.sess-item.long-press').forEach(el=> el.classList.remove('long-press'));
  });
  if(animate) applyStagger();
}

// In-place session-list update: reuse live rows, patch only what changed, never rebuild.
function patchRow(n, s){
  const sid=esc(s.session_id), raw=s._snippet||s.snippet||"";
  const name=sessName(s), tm=relTime(s.last_active), nameHtml=esc(name);
  let touched=false;
  n.classList.toggle('active', !!currentSid && sid===esc(currentSid));
  const nameEl=n.querySelector('.sess-name'), tmEl=n.querySelector('.sess-time');
  if(nameEl&&nameEl.textContent!==name){ nameEl.textContent=name; nameEl.title=nameHtml; touched=true; }
  if(tmEl&&tmEl.textContent!==tm){ tmEl.textContent=tm; touched=true; }
  const sn=n.querySelector('.sess-snippet');
  if(raw&&!sn){ const d=document.createElement('div'); d.className='sess-snippet'; d.innerHTML=esc(raw).replace(/&lt;b&gt;/g,'<b>').replace(/&lt;\/b&gt;/g,'</b>'); n.insertBefore(d, n.querySelector('.sess-del')); touched=true; }
  else if(raw&&sn){ const html=esc(raw).replace(/&lt;b&gt;/g,'<b>').replace(/&lt;\/b&gt;/g,'</b>'); if(sn.innerHTML!==html){ sn.innerHTML=html; touched=true; } }
  else if(!raw&&sn){ sn.remove(); touched=true; }
  return touched;
}
function newSessItem(s, act){
  const sid=esc(s.session_id), raw=s._snippet||s.snippet||"";
  const name=sessName(s), tm=relTime(s.last_active), nameHtml=esc(name);
  const snippetHtml=raw?`<div class="sess-snippet">${esc(raw).replace(/&lt;b&gt;/g,'<b>').replace(/&lt;\/b&gt;/g,'</b>')}</div>`:"";
  const n=document.createElement('div');
  n.className='sess-item'+(act?' active':'');
  n.dataset.sid=sid;
  n.innerHTML=`<div class="sess-name" aria-label="${nameHtml}">${nameHtml}</div><div class="sess-time">${tm}</div>${snippetHtml}<button class="sess-del" data-sid="${sid}" aria-label="${t('del')}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button>`;
  return n;
}
function patchSessionList(el, list){
  const cur=[...el.children].filter(n=>n.classList.contains('sess-item'));
  if(!cur.length) return false;
  const sameOrder=list.length===cur.length&&cur.every((n,i)=>n.dataset.sid===esc(list[i].session_id));
  if(sameOrder){
    // Same rows, same order: patch IN PLACE. Never detach nodes into a fragment —
    // a skipped replaceChildren would strand them (empty-but-present list).
    cur.forEach((n,i)=>patchRow(n, list[i]));
    return true;
  }
  const keyed=new Map(cur.map(n=>[n.dataset.sid,n]));
  const frag=document.createDocumentFragment();
  list.forEach(s=>{
    const sid=esc(s.session_id);
    const existing=keyed.get(sid);
    const n=existing||newSessItem(s, !!currentSid && sid===esc(currentSid));
    if(existing) patchRow(n, s);
    frag.append(n);
  });
  const sc=el.scrollTop;
  el.replaceChildren(frag);
  el.scrollTop=sc;
  return true;
}

function newSid(){ return 'session_'+Date.now()+'_'+crypto.getRandomValues(new Uint32Array(1))[0].toString(36); }
function newChat(){
  currentSid=null; document.querySelectorAll('.sess-item').forEach(el=>el.classList.remove('active'));
  document.getElementById('sess-title').textContent='piSynapse';
  clearMsgs(); closeSidebar();
  document.getElementById('msg-input').focus();
  document.getElementById('msg-input').style.height = 'auto';
  showWelcome();
}

async function loadSession(sid){
  currentSid=sid; clearMsgs(); closeSidebar();
  document.querySelectorAll('.sess-item').forEach(el=> el.classList.toggle('active', el.getAttribute('data-sid') === sid));
  const sess=sessionList.find(s=>s.session_id===sid);
  document.getElementById('sess-title').textContent=sess ? sessName(sess) : sid;
  try{
    const d=await api('GET','/chat/history?session_id='+encodeURIComponent(sid));
    const msgs=d.messages||[];
    if(msgs.length){ msgs.forEach(m=>addMsg(m.role,m.content,false,m.timestamp,m.images||null,m.reasoning||null,m.audits||null,m.id||null,m.feedback||null,m.feedback_note||null)); scrollEnd(true); refreshLastState(); } else showWelcomeMsg();
  } catch { showWelcomeMsg(); }
}

function triggerDelSession(sid){
  const sess = sessionList.find(s=>s.session_id===sid);
  showConfirmModal({ tool: 'delete_session', params: { sid: sid, name: sess ? sessName(sess) : sid } });
}

// ── Message Sending ─────────────────────────────────────────────────────────────
function createStreamBubble(){
  hideTyping();
  const g=document.createElement('div'); g.className='msg-group assistant';
  g.innerHTML=`<div class="msg-meta"><span class="who">piSynapse</span><span class="ts">${timeNow()}</span></div><div class="bubble"></div>`;
  document.getElementById('messages').appendChild(g); scrollEnd(true); _roundGroup=g; return g.querySelector('.bubble');
}

function renderThink(body, html){
  const near = body.scrollHeight - body.scrollTop - body.clientHeight < 60;
  body.innerHTML = html;
  if(near) body.scrollTop = body.scrollHeight;
}

function toggleThinkBox(box){
  const e = document.getElementById('messages');
  const wasNearBottom = e.scrollHeight - e.scrollTop - e.clientHeight < 150;
  box.classList.toggle('collapsed');
  box.classList.toggle('open');
  if(!box.classList.contains('collapsed')){
    const tb = box.querySelector('.think-body'); if(tb) tb.scrollTop = tb.scrollHeight;
    if(wasNearBottom) scrollEnd(true);
  }
}

function ensureThinkBox(bubble){
  const g = bubble.closest('.msg-group');
  let box = g.querySelector('.think-box');
  if(box) return box;
  box = document.createElement('div');
  box.className = 'think-box live collapsed';
  box.innerHTML = '<div class="think-head"><span class="chev">\u25B8</span><span class="lab"></span></div><div class="think-body"></div>';
  box.querySelector('.lab').textContent = t('thinkingLive');
  box.querySelector('.think-head').onclick = (e) => { e.stopPropagation(); toggleThinkBox(box); };
  g.insertBefore(box, bubble);
  return box;
}

async function abortStream(){
  const sid=_pendingStream?.sid || currentSid; if(!sid) return;
  userAborted=true;
  try{
    const h={'Content-Type':'application/json'}; const k=getApiKey(); if(k) h['X-API-Key']=k;
    await fetch(API+'/chat/abort/'+encodeURIComponent(sid), {method:'POST', headers:h});
  }catch{}
}

async function regenerate(group){
  if(loading) return;
  const sid=currentSid; if(!sid) return;
  // The assistant reply being regenerated belongs to its DIRECTLY preceding
  // user message — that pair is the branch point, not "the last user message".
  const ui=group.previousElementSibling;
  const uiIsUser=!!(ui && ui.classList && ui.classList.contains('msg-group') && ui.classList.contains('user'));
  const userText=uiIsUser ? (ui.querySelector('.bubble')?.textContent||'').trim() : '';
  if(!uiIsUser || !userText) return;
  const mid=parseInt(group.dataset.mid||'',10)||null;
  if(!mid){
    // No DB anchor (aborted/legacy message) — only the last exchange can be
    // re-rolled safely with the old "delete last assistant" endpoint.
    if(group!==document.querySelector('#messages .msg-group.assistant:last-of-type')) return;
    try{ await fetch(API+'/chat/messages/last/'+encodeURIComponent(sid),{method:'DELETE',headers:apiHeaders()}); }catch{}
    group.remove(); ui.remove();
  } else {
    // Branch semantics: truncate DB + DOM from this message onward. The
    // original prompt stays in the DB (its id < anchor) and the re-run appends
    // a fresh reply at the same position — old tail never reappears in context.
    try{ await api('DELETE','/chat/messages/branch/'+encodeURIComponent(sid),{message_id:mid}); }catch{}
    for(let node=group; node;){ const next=node.nextElementSibling; node.remove(); node=next; }
    refreshLastState();
  }
  await sendMsg({ regenText: userText });
}

function apiHeaders(){ const h={'Content-Type':'application/json'}; const k=getApiKey(); if(k) h['X-API-Key']=k; return h; }

async function sendMsg(opts){
  if(loading){ if(_pendingStream) abortStream(); return; }
  userAborted=false;
  const el=document.getElementById('msg-input');
  // Per-message regenerate passes the prompt directly and keeps the original
  // user bubble (no second bubble, the server already holds that prompt).
  const text=(opts && opts.regenText) ? opts.regenText.trim() : el.value.trim();
  const images=pendingImages.map(i=>i.base64);
  if(!text && !images.length) return; if(!currentSid) currentSid=newSid();
  const sid = currentSid;
  // Optimistic RAKE title: show in sidebar instantly, before model responds
  if(!sessionList.find(s=>s.session_id===sid)){
    const rakeTitle=generateRakeTitleJS(text);
    const newSess={session_id:sid, name:rakeTitle, last_active:new Date().toISOString(), message_count:1};
    sessionList.unshift(newSess);
    renderSessions(sessionList, false); // silent: never replay the whole-list slide-in on an optimistic insert
    document.getElementById('sess-title').textContent=rakeTitle;
  }
  _pendingStream = { sid };
  clearToolPills(); // fresh round: the CURRENT round's transient rows are dropped (settled rows persist)
  _roundGroup=null;
  el.value=''; el.style.height='auto'; pendingImages=[]; renderImagePreview();
  if(!(opts && opts.regenText)) addMsg('user',text,true,null,images);
  showTyping(); setLoading(true); refreshLastState();
  let bubble=null, fullText='', thinkBox=null, fullReasoning='';
  let gotReply=false, terminated=false, toolRow=null, roundAudits=[], roundVerifWarn=false, noteGroup=null;
  // ⚠️ YENİ DAL EKLEME: done/confirm/error/catch — hepsi terminal durumdur.
  // Yeni bir son durum dalı eklersen, return'den ÖNCE `terminated=true` ekle.
  // Aksi halde finally bloğu gereksiz "boş yanıt" mesajı ekler.
  try{
    const headers={'Content-Type':'application/json'};
    const _k=getApiKey(); if(_k) headers['X-API-Key']=_k;
    const originFlag = _chipOrigin ? 'chip' : ''; _chipOrigin = false;
    const _payload = { message: text, session_id: sid, user_id: config.username||'default', think_mode: thinkMode, images: images||[], reasoning_effort: thinkEffort, origin: originFlag };
    const _resp = _NATIVE ? await _nativeSSEResponse(Object.assign({}, _payload, { system: _nativeSystem(), messages: _nativeHistory.slice(-12) })) : await fetch(API+'/chat/stream',{ method:'POST', headers, body: JSON.stringify(_payload) });
    if(!_resp.ok) throw new Error('HTTP '+_resp.status);
    const reader=_resp.body.getReader(), dec=new TextDecoder(); let buf='';
    while(true){
      const {done,value}=await reader.read(); if(done) break;
      buf+=dec.decode(value,{stream:true}); const lines=buf.split('\n'); buf = lines.pop() || '';
      for(const rawLine of lines){
        const line = rawLine.trim(); if(!line || !line.startsWith('data: ')) continue;
        let data; try{ data=JSON.parse(line.slice(6)); } catch{ continue; }
        if('token' in data){
          if(currentSid !== sid) continue; // user navigated away, skip rendering
          // Each settled tool row is this message's feedback (✓/⚠ + optional
          // mark affordance). Rows are dropped on the NEXT send, not here.
          if(!bubble){ bubble=createStreamBubble(); }
          gotReply=true;
          // Tool finished — the model is now answering. Drop the working label
          // ("notlarına bakıyorum…") the moment text starts: the row flips to
          // its quiet feedback state. Multi-step revives it on the next tool
          // event and the following token re-settles (no second row).
          if(toolRow && toolRow.isConnected && !toolRow.classList.contains('done')){
            settleFeedbackRow(toolRow, true, roundAudits, roundVerifWarn);
          }
          fullText+=data.token; bubble.innerHTML=withStreamCaret(renderMd(fullText)); scrollEnd(false);
        } else if(data.done){
          if(thinkBox && fullReasoning){
            const body = thinkBox.querySelector('.think-body');
            renderThink(body, renderMd(fullReasoning));
            thinkBox.classList.remove('live');
            thinkBox.classList.add('collapsed');
            const head = thinkBox.querySelector('.think-head');
            head.querySelector('.lab').textContent = t('thinkingTitle');
            head.onclick = e => { e.stopPropagation(); toggleThinkBox(thinkBox); };
          }
          if(!gotReply && !terminated){
            terminated=true;
            if(bubble) bubble.textContent='\u26A0\uFE0F '+t('emptyReply'); else addMsg('assistant','\u26A0\uFE0F '+t('emptyReply'));
          }
          terminated=true;
          // Branch anchor for per-message regenerate: remember the saved
          // DB id on this bubble so regen can truncate context from it.
          if(bubble && data.message_id) bubble.closest('.msg-group').dataset.mid=String(data.message_id);
          // Title is set by backend (first 4 words instant + LLM enriched background if enabled).
          // Frontend must NOT call PATCH to override it.
          await loadSessions(false);
          if(_NATIVE) _nativeChatSave();
          // Enriched title arrives ~4-5s later via background LLM — refresh again if smart title on
          if(config.llm_title_enrichment !== 'off'){
            setTimeout(async()=>{
              await loadSessions(false);
              const s=sessionList.find(x=>x.session_id===sid);
              if(s && currentSid===sid) document.getElementById('sess-title').textContent=sessName(s);
            }, 5500);
          }
          // Don't reload the session — the stream bubble already has the full text.
          // Reloading calls clearMsgs()+DOM rebuild, which causes a visible flash.
          // If the user navigated away during streaming, loadSessions() updates the sidebar.
        } else if('reasoning' in data){
          if(currentSid !== sid) continue;
          // Thinking streams after tool calls — the feedback row stays under
          // the message (it is the marking target). Cleared on the next send.
          if(!bubble) bubble=createStreamBubble();
          // Same as the token path: once the model starts producing output
          // (here: thinking) the tool label is done — settle the row.
          if(toolRow && toolRow.isConnected && !toolRow.classList.contains('done')){
            settleFeedbackRow(toolRow, true, roundAudits, roundVerifWarn);
          }
          if(!thinkBox){ thinkBox=ensureThinkBox(bubble); }
          fullReasoning+=data.reasoning;
          renderThink(thinkBox.querySelector('.think-body'),
            withStreamCaret(renderMd(fullReasoning)));
          scrollEnd(false);
        } else if(data.tool){
          if(currentSid !== sid) continue;
          if(!bubble) bubble=createStreamBubble();
          if(data.tool.phase==='end'){
            toolRow=showToolScan(toolRow, data.tool);
            // Claimed success is NOT ground truth for scope tools (D-1): a
            // create/update without a backend-verified read-back (unverified)
            // or a store/read mismatch (verification_failed) must not produce a
            // green-alongside confirmation affordance. Those rounds settle as
            // the "could not verify" warn state instead, and their audits are
            // excluded from the 👍 pair. Non-scope tools carry no
            // verification_status → unchanged behaviour.
            const vs=data.tool.verification_status;
            const verifiedOk=data.tool.ok && (vs==null || vs==='verified' || vs==='verified_by_fallback');
            if(verifiedOk && data.tool.audit_id!=null && data.tool.audit_id!=='') roundAudits.push({audit:data.tool.audit_id, name:data.tool.name});
            if(data.tool.ok && (vs==='unverified' || vs==='verification_failed')) roundVerifWarn=true;
          }
          else { toolRow=showToolScan(toolRow, data.tool); }
        } else if(data.gen_retry){
          if(currentSid !== sid) continue;
          if(!bubble) bubble=createStreamBubble();
          toolRow=showGenRetry(toolRow, data.gen_retry.reason);
        } else if(data.confirm){
          terminated=true; hideTyping(); showConfirmModal(data.confirm); setLoading(false); _pendingStream=null; return;
        } else if(data.error){
          terminated=true; hideTyping();
          // Adım 3: don't collapse every backend error into the generic
          // "Sunucuya ulaşılamadı" (connErr). Show the actual failure — only a
          // real connection drop is a connection problem; anything else (context
          // overflow, generation failure…) is its own, specific recoverable error.
          const isConnErr = /connection error/i.test(data.error);
          const eMsg = isConnErr ? t('errConnLost')
            : /context too long/i.test(data.error) ? t('errContextTooLong')
            : data.error;
          const errText = '\u26A0\uFE0F '+eMsg;
          if(bubble){ bubble.textContent=errText; }
          else { noteGroup=addMsg('assistant',errText); }
          toast(isConnErr ? t('connErr') : eMsg, true); setLoading(false); _pendingStream=null; return;
        }
      }
    }
  } catch{
    terminated=true;
    if(currentSid === sid){
      hideTyping(); if(bubble) bubble.textContent='\u26A0\uFE0F '+t('connErr'); else noteGroup=addMsg('assistant','\u26A0\uFE0F '+t('connErr')); toast(t('connErr'),true);
    }
  } finally{
    if(_pendingStream?.sid === sid) _pendingStream=null;
    if(toolRow && toolRow.isConnected && !toolRow.classList.contains('done')){
      // Round over: settle the single feedback row with the thumbs collected
      // from every tool that actually ran and got an audit. A refused or
      // interrupted round has no audits — fall back to the plain ✓/⚠ state.
      settleFeedbackRow(toolRow, !!gotReply, roundAudits, roundVerifWarn);
    }
    toolRow=null; _roundGroup=null;
    typingEl?.classList.remove('tool-pending');
    if(!gotReply && !terminated){
      if(currentSid === sid){
        const note = userAborted ? '\u2139\uFE0F '+t('stoppedMsg') : '\u26A0\uFE0F '+t('emptyReply');
        if(bubble) bubble.textContent=note;
        else noteGroup=addMsg('assistant',note);
      }
    }
    if(userAborted && currentSid === sid){
      // Abort closes the SSE without a done event — do the light
      // session bookkeeping here so sidebar stays consistent.
      // Backend already set the first-4-words title on first message.
      await loadSessions(false);
      if(config.llm_title_enrichment !== 'off'){
        setTimeout(async()=>{
          await loadSessions(false);
          const s=sessionList.find(x=>x.session_id===sid);
          if(s && currentSid===sid) document.getElementById('sess-title').textContent=sessName(s);
        }, 5500);
      }
    }
    if(currentSid === sid){
      // Universal feedback: a round that never had a tool row still gets its
      // one 👍/👎 pair here (the copy/listen/regen bar merges in below).
      ensureRoundFeedback(bubble ? bubble.closest('.msg-group') : noteGroup, !!gotReply);
      // Stream finished: drop the caret, keep final markdown render
      if(bubble && fullText) bubble.innerHTML = renderMd(fullText);
      // Add copy/TTS actions to the streamed message (createStreamBubble adds none)
      if(bubble && fullText) attachMsgActions(bubble.closest('.msg-group'), fullText);
      refreshLastState();
      setLoading(false); el.focus();
      // Auto-speak response if voice input + auto-TTS enabled
      if(lastInputWasVoice && config.auto_tts_on_voice === 'on' && fullText){
        lastInputWasVoice = false;
        const ttsBtnEl = document.querySelector('.msg-group.assistant:last-child .tts-btn');
        if(ttsBtnEl) toggleTTS(fullText, ttsBtnEl);
      }
      lastInputWasVoice = false;
    }
  }
}

function setLoading(v){
  loading=v;
  document.body.classList.toggle('generating', v);
  const dot=document.getElementById('status-dot'), btn=document.getElementById('send-btn');
  // While a chat stream is running the send button doubles as a stop button
  // (standard chat UX); other flows keep the plain disabled look.
  const stoppable=v && !!(_pendingStream && _pendingStream.sid);
  btn.classList.toggle('stop', stoppable);
  btn.disabled=v && !stoppable;
  btn.title=stoppable ? t('stopGen') : t('send');
  btn.innerHTML=stoppable ? STOP_ICON : SEND_ICON;
  if(v){ dot.classList.remove('ok','warn','error'); dot.classList.add('thinking'); } else { dot.classList.remove('thinking'); pollHealth(); }
  // Aurora hız kolu: blob animasyonlarının oynatma hızı üretilirken artar,
  // biterken normale döner. playbackRate değişimi kare atlattırmaz (faz korunur).
  requestAnimationFrame(()=>{
    document.querySelectorAll('#aurora .ab').forEach(el=>{
      el.getAnimations().forEach(a=>{ try{ a.playbackRate = v ? 2.3 : 1; }catch(e){} });
    });
  });
}
 const _SPEAKER_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>';
const _CLIPBOARD_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
const _REGEN_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>';
const _CHECK_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
const _THUMB_UP_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 10v12"></path><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z"></path></svg>';
const _THUMB_DOWN_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 14V2"></path><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z"></path></svg>';

async function copyMessage(text, btn){
  let ok = true;
  try{
    await navigator.clipboard.writeText(text);
  }catch(e){
    // Clipboard API unavailable (non-secure context) — execCommand fallback.
    try{
      const ta=document.createElement('textarea');
      ta.value=text; ta.style.position='fixed'; ta.style.opacity='0';
      document.body.appendChild(ta); ta.select();
      ok=document.execCommand('copy'); ta.remove();
    }catch(e2){ ok=false; }
  }
  if(btn && ok){
    btn.classList.add('copied');
    const prev=btn.innerHTML;
    btn.innerHTML=_CHECK_SVG; btn.title=t('copiedTitle');
    setTimeout(()=>{ btn.classList.remove('copied'); btn.innerHTML=prev; btn.title=t('copyTitle'); },1400);
  }
}

function attachMsgActions(group, text){
  // Copy + listen + regenerate buttons under assistant messages. When the
  // message made an audited tool call, its settled feedback row IS the action
  // bar: these buttons merge into the same row as the thumbs (one flat bar,
  // same size/style/color, separated only by a hairline divider).
  if(!group || group.querySelector('.msg-actions')) return;
  const copyBtn=document.createElement('button');
  copyBtn.className='tts-btn copy-btn'; copyBtn.title=t('copyTitle');
  copyBtn.innerHTML=_CLIPBOARD_SVG;
  copyBtn.onclick=()=>copyMessage(text,copyBtn);
  const ttsBtn=document.createElement('button');
  ttsBtn.className='tts-btn'; ttsBtn.title=t('listenTitle');
  ttsBtn.innerHTML=_SPEAKER_SVG;
  ttsBtn.onclick=()=>toggleTTS(text,ttsBtn);
  const regenBtn=document.createElement('button');
  regenBtn.className='tts-btn regen-btn'; regenBtn.title=t('regenTitle');
  regenBtn.innerHTML=_REGEN_SVG;
  regenBtn.onclick=()=>regenerate(group);
  // Per-message branching (C-12): every assistant message may be re-rolled —
  // regen anchors on the message's DB id. Only messages without an anchor
  // (aborted/legacy rounds) fall back to the last-exchange rule.
  const canRegen=regenerateEligible(group);
  const settled=group.querySelector('.tool-status.done');
  if(settled && !settled.querySelector('.copy-btn')){
    const div=document.createElement('span'); div.className='bar-divider';
    settled.prepend(div);
    const btns=[copyBtn,ttsBtn];
    if(canRegen) btns.push(regenBtn);
    for(let i=btns.length-1;i>=0;i--) settled.prepend(btns[i]);
    return;
  }
  const row=document.createElement('div'); row.className='msg-actions';
  row.appendChild(copyBtn); row.appendChild(ttsBtn);
  if(canRegen) row.appendChild(regenBtn);
  group.appendChild(row);
}

function regenerateEligible(group){
  if(parseInt(group.dataset.mid||'',10)) return true;
  return group===document.querySelector('#messages .msg-group.assistant:last-of-type');
}

function refreshLastState(){
  const assistants=[...document.querySelectorAll('#messages .msg-group.assistant')];
  assistants.forEach(g=>{
    const bar=g.querySelector('.msg-actions')||g.querySelector('.tool-status.done');
    if(bar) bar.classList.toggle('not-last', g!==assistants[assistants.length-1]);
  });
}

function addMsg(role, content, forceScroll=true, ts=null, images=null, reasoning=null, audits=null, mid=null, feedback=null, fbNote=null){
  document.querySelector('.welcome')?.remove();
  const g=document.createElement('div'); g.className='msg-group '+role;
  if(mid) g.dataset.mid=String(mid);
  const who=role==='user' ? (config.username||t('you')) : 'piSynapse';
  const timeLabel = ts ? relTime(ts) : timeNow();
  g.innerHTML=`<div class="msg-meta"><span class="who">${esc(who)}</span><span class="ts">${timeLabel}</span></div><div class="bubble"></div>`;
  const b=g.querySelector('.bubble');
  if(images && images.length){
    const imgDiv=document.createElement('div'); imgDiv.className='bubble-images';
    images.forEach(b64 => { const img=document.createElement('img'); img.src='data:image/jpeg;base64,'+b64; imgDiv.appendChild(img); });
    b.appendChild(imgDiv);
  }
  if(reasoning){
    const box=document.createElement('div'); box.className='think-box collapsed';
    box.innerHTML='<div class="think-head"><span class="chev">\u25B8</span><span class="lab"></span></div><div class="think-body"></div>';
    box.querySelector('.lab').textContent = t('thinkingTitle');
    renderThink(box.querySelector('.think-body'), renderMd(reasoning));
    const head=box.querySelector('.think-head');
    head.onclick=()=>toggleThinkBox(box);
    g.insertBefore(box, b);
  }
  if(role==='assistant'){
    b.innerHTML+=renderMd(content);
  } else if(content) b.appendChild(document.createTextNode(content));
  document.getElementById('messages').appendChild(g);
  if(role==='assistant'){
    // Historical messages always restore their single feedback row (universal
    // thumbs, C-12): audited rounds get the audit-bound pair with persisted
    // correction/confirmation state, tool-less rounds the message-level pair.
    // The copy/listen/regen bar merges into that row below, like live messages.
    const sfb=document.createElement('div'); sfb.className='tool-status';
    g.appendChild(sfb);
    settleFeedbackRow(sfb, true, audits && audits.length ? audits.map(a=>({audit:a.audit_id, name:a.tool_name})) : []);
    if(audits && audits.length) applyFeedbackState(sfb, audits);
    else applyMsgFeedbackState(sfb, feedback, fbNote);
    attachMsgActions(g, content);
  }
  scrollEnd(forceScroll);
  return g;
}

function applyFeedbackState(row, audits){
  // Persisted signals: every audit confirmed → up thumb stays lit; any audit
  // corrected → down thumb stays marked. Mirrors the live click outcome.
  const up=row.querySelector('.fb-up');
  if(up && audits.length && audits.every(a=>a.confirmed_at)){
    up.classList.add('active'); up.title=t('markConfirmDone');
  }
  const down=row.querySelector('.mark-btn');
  if(down && audits.some(a=>a.corrected_at)){
    down.classList.add('marked'); down.title=t('markDone');
  }
}

function showTyping(){
  // Neutral activity dots only — no "thinking" label. It showed regardless of
  // think mode (misleading); real reasoning gets its own collapsible box.
  const g=document.createElement('div'); g.className='msg-group assistant'; g.id='typing-row';
  g.innerHTML='<div class="typing"><span></span><span></span><span></span></div>';
  document.getElementById('messages').appendChild(g); scrollEnd(true); typingEl=g;
}
function hideTyping(){ typingEl?.remove(); typingEl=null; }

function placeRow(row){
  // The feedback row lives INSIDE the assistant message group, directly below
  // its bubble — in-flow with the text, never floating over the chat.
  const host=(_roundGroup && _roundGroup.isConnected) ? _roundGroup : document.getElementById('messages');
  if(host) host.appendChild(row);
  scrollEnd(false);
  return row;
}
function resetPill(row){
  // Reuse path: a settled row (thumbs/✓/⚠, no live spinner) must look active
  // again before its label is swapped for the next event. A done row being
  // reused (gen_retry revival) also surrenders its feedback thumbs — it is no
  // longer this round's marking target. The merged copy/listen/regen bar is
  // message-level, so it stays.
  row.classList.remove('ok','done');
  row.querySelector('.mark-btn')?.remove();
  row.querySelector('.fb-up')?.remove();
  row.querySelector('.bar-divider')?.remove();
  delete row.dataset.audit;
  delete row.dataset.audits;
  delete row.dataset.fb;
  row.querySelectorAll('.fb-state').forEach(s=>s.remove());
  let sp=row.querySelector('.tspin');
  if(!sp){ sp=document.createElement('span'); sp.className='tspin'; row.prepend(sp); }
  else sp.classList.remove('dead');
  let lab=row.querySelector('.tlab');
  if(!lab){ lab=document.createElement('span'); lab.className='tlab'; row.appendChild(lab); }
}
function ensureToolRow(toolRow){
  // One row per message: reuse the same pill through the whole round — the
  // label swaps for each tool while the spinner stays. It settles once when the
  // model starts replying (token/reasoning) and is REVIVED on a later tool
  // event (multi-step), so the message owns a SINGLE 👍/👎 pair (C-7).
  if(toolRow && toolRow.isConnected){
    if(toolRow.classList.contains('done')) resetPill(toolRow);
    return toolRow;
  }
  const row=document.createElement('div'); row.className='tool-status';
  row.innerHTML='<span class="tspin"></span><span class="tlab"></span>';
  placeRow(row);
  if(typingEl){ typingEl.classList.add('tool-pending'); }
  return row;
}
function showToolScan(toolRow, info){
  const row=ensureToolRow(toolRow);
  row.querySelector('.tspin')?.classList.remove('dead');
  const lab=row.querySelector('.tlab');
  let txt=toolLabel(info.name);
  if(info.phase==='refused'){
    txt+=' — '+t('toolCap')+' ('+info.attempt+'/'+info.max+')';
  } else if((info.attempt||1)>1){
    txt+=' ('+t('toolAttempt')+' '+info.attempt+'/'+info.max+')';
  } else {
    txt+='…';
  }
  if(info.phase==='end'){
    if(info.noop){
      // NOOP (D-3): the target no longer existed, so the mutation changed
      // nothing. success=0, but this is NOT an error — show a neutral info
      // state instead of a red failure, and keep the round markable.
      row.classList.remove('ok','warn');
      row.classList.add('noop');
      txt=t('noopInfo');
    } else if(info.clarify){
      // CLARIFY_REQUIRED tools are now success=0 (D-1a): show a neutral
      // info state instead of a red failure, and the round stays markable.
      row.classList.remove('ok','warn');
      row.classList.add('clarify');
      txt=t('clarifyAsked');
    } else {
      txt=txt.replace(/…$/,'');
    }
  }
  lab.textContent=txt;
  if(info.phase==='end') row.querySelector('.tspin')?.classList.add('dead');
  scrollEnd(false);
  return row;
}

function settleFeedbackRow(row, ok, audits, warn){
  // Round-finalize: toggle state, drop the spinner, then render the feedback.
  // With audits the pair is the C-7 one → many (single 👎/👍 per message);
  // without (refused/interrupted round) keep the quiet ✓ (⚠ stays with label).
  if(!row || !row.isConnected) return row;
  if(row.classList.contains('noop')){
    // D-3: the mutation was an idempotent no-op (target already gone). success=0
    // but NOT an error — keep the neutral info label set in showToolScan, drop the
    // spinner, and render no confirmation pair (nothing changed to confirm).
    row.classList.remove('ok'); row.classList.add('done');
    row.querySelector('.tspin')?.remove();
    row.querySelectorAll('.fb-state').forEach(s=>s.remove());
    return row;
  }
  if(warn){
    // D-1: a scope tool that ran but could not be backend-verified (unverified
    // or verification_failed) settles as an amber warning, NOT a green success.
    // No thumbs: the "correct" signal would be a lie, and the down-mark would
    // drop CLARIFY-style on a row that never got an audit. Label + warn text.
    row.classList.remove('ok','clarify'); row.classList.add('warn','done');
    row.querySelector('.tspin')?.remove();
    row.querySelectorAll('.fb-state').forEach(s=>s.remove());
    row.querySelector('.tlab')?.remove();
    const w=document.createElement('span');
    w.className='fb-state';
    w.textContent='\u26A0 '+t('verifFail');
    row.appendChild(w);
    return row;
  }
  row.classList.toggle('ok', !!ok);
  row.classList.add('done');
  row.querySelector('.tspin')?.remove();
  row.querySelectorAll('.fb-state').forEach(s=>s.remove());
  if(ok){
    row.querySelector('.tlab')?.remove();
  } else {
    const lab=row.querySelector('.tlab');
    if(lab) lab.textContent=lab.textContent.replace(/…$/,'');
  }
  if(audits && audits.length){
    row.dataset.audit=String(audits[0].audit);
    row.dataset.audits=audits.map(a=>a.audit).join(',');
    // Retry-revived rows keep their merged copy/listen/regen bar — reintroduce
    // the divider so the re-added thumbs stay visually grouped.
    if(row.querySelector('.copy-btn')){
      const d=document.createElement('span'); d.className='bar-divider'; row.appendChild(d);
    }
    row.appendChild(makeThumbUpBtn(row, audits.slice()));
    row.appendChild(makeMarkBtn(row, audits.slice()));
  } else {
    // Universal thumbs (C-12 feedback): no audited tool call ran, but the
    // round is still markable — a dropped intent, a clarifying-question reply
    // or a hallucinated no-tool answer all become recorded data.
    row.appendChild(makeMsgThumbUpBtn(row));
    row.appendChild(makeMsgDownBtn(row));
  }
  return row;
}

let _toolGroupsCache=null; let _roundGroup=null;
function clearToolPills(){ document.querySelectorAll('#messages .tool-status:not(.done), #messages .fb-tabs').forEach(r=>r.remove()); }

function makeMarkBtn(row, audits){
  const b=document.createElement('button');
  b.className='mark-btn fb-thumb tts-btn'; b.dataset.audit=String(audits[0].audit);
  b.innerHTML=_THUMB_DOWN_SVG;
  b.title=t('markWrong');
  b.onclick=()=>{
    // Single ran tool → straight to the familiar picker (keeps the keyboard
    // flow: Enter opens it, Tab reaches the first option). Multiple → first
    // pick WHICH tool was wrong, then the same picker bound to that audit.
    audits.length<=1 ? openGroupPicker(row, b, audits[0].audit)
                     : openFeedbackTabs(row, b, audits);
  };
  return b;
}
function makeThumbUpBtn(row, audits){
  const b=document.createElement('button');
  b.className='fb-up fb-thumb tts-btn';
  b.innerHTML=_THUMB_UP_SVG;
  b.title=t('markConfirm');
  b.onclick=()=>submitConfirmation(row, b, audits);
  return b;
}
async function submitConfirmation(row, btn, audits){
  // "Doğruydu": EVERY hardware-affecting tool that ran gets a positive
  // (confirmation) signal — one decision, N sequential calls. A partial
  // failure leaves the thumb unlit so the user can retry the whole batch;
  // success also clears any stored mark and drops the correction chooser.
  btn.disabled=true;
  try{
    for(const a of (audits||[])) await api('POST','/chat/tool-confirm',{audit_id:a.audit});
    btn.classList.add('active');
    btn.title=t('markConfirmDone');
    const down=row.querySelector('.mark-btn');
    if(down){ down.classList.remove('marked'); down.title=t('markWrong'); }
    row.parentNode?.querySelectorAll('.fb-tabs').forEach(el=>el.remove());
  } catch(e){
    if(e && e.message && e.message.startsWith('HTTP ')) toast(t('markConfirmErr')+': '+e.message.slice(5), true);
    else toast(t('markConfirmErr'), true);
  }
  btn.disabled=false;
}

// ── Universal thumbs (message-level feedback) ─────────────────────────────────
// Tool-less rounds (or rounds whose audits never materialized) still show a
// 👍/👎 pair. Marking records a verdict on the message itself via
// /chat/message-feedback — one row per message; a 👎 accepts an optional note
// capturing WHY it was wrong (model dropped the intent, asked instead of
// acting, hallucinated a no-tool reply, …). Without a DB anchor (mid) the
// thumbs still respond locally but cannot persist.
function makeMsgThumbUpBtn(row){
  const b=document.createElement('button');
  b.className='fb-up fb-thumb tts-btn';
  b.innerHTML=_THUMB_UP_SVG;
  b.title=t('markConfirm');
  b.onclick=()=>msgMarkUp(row, b);
  return b;
}
function makeMsgDownBtn(row){
  const b=document.createElement('button');
  b.className='mark-btn fb-thumb tts-btn';
  b.innerHTML=_THUMB_DOWN_SVG;
  b.title=t('markWrong');
  b.onclick=()=>msgMarkDown(row, b);
  return b;
}
function msgMid(row){ return parseInt((row.closest('.msg-group')||row).dataset.mid||'',10)||null; }
async function msgMarkUp(row, btn){
  removeMsgNoteEditor(row);
  const mid=msgMid(row);
  if(mid){
    try{ await api('POST','/chat/message-feedback',{message_id:mid,value:'up'}); }
    catch(e){ toast((e && e.message && e.message.startsWith('HTTP ')) ? t('markConfirmErr')+': '+e.message.slice(5) : t('markConfirmErr'), true); return; }
  }
  btn.classList.add('active'); btn.title=t('markConfirmDone');
  const down=row.querySelector('.mark-btn');
  if(down){ down.classList.remove('marked','msg-note'); down.title=t('markWrong'); delete down.dataset.note; }
}
async function msgMarkDown(row, btn){
  removeMsgNoteEditor(row);
  const mid=msgMid(row);
  if(mid){
    try{ await api('POST','/chat/message-feedback',{message_id:mid,value:'down'}); }
    catch(e){ toast((e && e.message && e.message.startsWith('HTTP ')) ? t('markErr')+': '+e.message.slice(5) : t('markErr'), true); return; }
  }
  setMsgDown(row, btn);
  openMsgNoteEditor(row, btn);
}
function setMsgDown(row, btn){
  btn.classList.add('marked'); btn.title=t('markDone');
  const up=row.querySelector('.fb-up');
  if(up){ up.classList.remove('active'); up.title=t('markConfirm'); }
}
function clearMsgDown(row){
  const down=row.querySelector('.mark-btn');
  if(down){ down.classList.remove('marked','msg-note'); down.title=t('markWrong'); delete down.dataset.note; }
}
function ensureRoundFeedback(group, ok){
  // A message group with no feedback row yet gets the universal message-level
  // pair. Tool rounds already settled their audit row, so this is a no-op.
  if(!group || !group.isConnected) return;
  if(group.querySelector('.tool-status, .msg-actions')) return;
  const row=document.createElement('div'); row.className='tool-status';
  row.innerHTML='<span class="tlab"></span>';
  group.appendChild(row);
  settleFeedbackRow(row, !!ok, []);
}
function openMsgNoteEditor(row, btn){
  document.querySelector('#messages .msg-note-editor')?.remove();
  const editor=document.createElement('div'); editor.className='msg-note-editor';
  const inp=document.createElement('input'); inp.type='text'; inp.placeholder=t('notePlaceholder');
  inp.value=btn.dataset.note||'';
  const save=document.createElement('button'); save.className='note-save'; save.textContent=t('noteSave');
  const cancel=document.createElement('button'); cancel.className='note-cancel'; cancel.textContent=t('noteCancel');
  const commit=async()=>{
    const note=inp.value.trim();
    const mid=msgMid(row);
    if(mid){
      try{ await api('POST','/chat/message-feedback',{message_id:mid,value:'down',note:note||null}); }
      catch(e){ toast((e && e.message && e.message.startsWith('HTTP ')) ? t('markErr')+': '+e.message.slice(5) : t('markErr'), true); return; }
    }
    if(note){ btn.classList.add('msg-note'); btn.dataset.note=note; btn.title=note; }
    else { btn.classList.remove('msg-note'); delete btn.dataset.note; btn.title=t('markDone'); }
    editor.remove();
  };
  save.onclick=commit;
  cancel.onclick=()=>editor.remove();
  inp.addEventListener('keydown', e=>{
    if(e.key==='Enter'){ e.preventDefault(); commit(); }
    else if(e.key==='Escape'){ editor.remove(); }
  });
  editor.append(inp, save, cancel);
  const host=row.parentNode || document.getElementById('messages');
  if(row.after) row.after(editor); else host.appendChild(editor);
  inp.focus(); inp.select();
}
function removeMsgNoteEditor(row){
  row?.parentNode?.querySelectorAll('.msg-note-editor').forEach(el=>el.remove());
  document.querySelector('#messages .msg-note-editor')?.remove();
}
function applyMsgFeedbackState(row, value, note){
  if(value==='up'){
    const up=row.querySelector('.fb-up');
    if(up){ up.classList.add('active'); up.title=t('markConfirmDone'); }
  } else if(value==='down'){
    const down=row.querySelector('.mark-btn');
    if(down){
      down.classList.add('marked');
      if(note){ down.classList.add('msg-note'); down.dataset.note=note; down.title=note; }
      else down.title=t('markDone');
    }
  }
}

function openFeedbackTabs(row, btn, audits){
  // 👎 with several tools: show which tools actually ran (each owns a live
  // audit_id). Clicking a chip opens the group picker bound to THAT tool only —
  // fixes correct only what was wrong and leaves the rest unreviewed (user
  // decision: no implicit confirmation).
  document.querySelectorAll('#messages .group-picker, #messages .fb-tabs').forEach(el=>el.remove());
  const tabs=document.createElement('div'); tabs.className='fb-tabs';
  const cap=document.createElement('span'); cap.className='fb-tabs-cap';
  cap.textContent=t('fbWhich'); tabs.appendChild(cap);
  for(const a of audits){
    const tb=document.createElement('button'); tb.type='button';
    tb.className='fb-tab'; tb.dataset.audit=String(a.audit); tb.dataset.tool=a.name;
    tb.textContent=toolShort(a.name);
    tb.onclick=()=>openGroupPicker(row, btn, a.audit, {after:tabs, onOk:(inf)=>finishTabCorrection(tb, a)});
    tabs.appendChild(tb);
  }
  const host=row.parentNode || document.getElementById('messages');
  if(row.after) row.after(tabs); else host.appendChild(tabs);
  tabs.scrollIntoView({block:'nearest', behavior:'smooth'});
  const dismiss=ev=>{
    // Never steal interaction from the open picker: gp-opt/save clicks live
    // OUTSIDE the chip strip and must not tear it down mid-interaction (a
    // removal would reflow the layout and swallow the click). Outside taps
    // close the strip; the picker's own dismiss handles itself.
    if(tabs.contains(ev.target)) return;
    if(ev.target.closest && ev.target.closest('.group-picker')) return;
    tabs.remove();
    document.removeEventListener('pointerdown',dismiss,true);
  };
  document.addEventListener('pointerdown',dismiss,true);
}
function finishTabCorrection(tb, a){
  // Mark the corrected tool's chip so the user sees which one is fixed while
  // the other chips stay available for additional corrections.
  tb.classList.add('done'); tb.title=t('markDone');
  tb.textContent=toolShort(a.name)+' \u2713';
}

function openGroupPicker(row, btn, auditId, opts={}){
  // A message owns at most one open picker — close any sibling first.
  document.querySelector('#messages .group-picker')?.remove();
  const panel=document.createElement('div'); panel.className='group-picker';
  let sel='';
  const render=()=>{
    panel.innerHTML='';
    const list=document.createElement('div'); list.className='gp-list';
    for(const g of (_toolGroupsCache||[])){
      const o=document.createElement('button'); o.className='gp-opt'+(g===sel?' sel':'');
      o.textContent=groupLabel(g);
      o.onclick=()=>{ sel=g; render(); };
      list.appendChild(o);
    }
    panel.appendChild(list);
    // Footer pinned below the scrollable option list: primary filled Save,
    // ghost Cancel. Never clipped — the card caps its height and scrolls
    // through the list instead.
    const foot=document.createElement('div'); foot.className='gp-foot';
    const saveEl=document.createElement('button'); saveEl.className='gp-save';
    saveEl.textContent=t('markSave'); saveEl.disabled=!sel;
    saveEl.onclick=()=>submitCorrection(row, btn, auditId, sel, panel, saveEl, opts);
    const cancelEl=document.createElement('button'); cancelEl.className='gp-cancel';
    cancelEl.textContent=t('cancel');
    cancelEl.onclick=()=>panel.remove();
    foot.appendChild(saveEl); foot.appendChild(cancelEl);
    panel.appendChild(foot);
  };
  const doOpen=()=>{
    sel=''; render();
    // In-flow: the picker inserts right after the feedback row (or, in the
    // multi-tool flow, after the tool-chip strip), inside the same message
    // group — static positioning so it pushes the chat down and never overlaps
    // the bubble. The old "clamp+flip" survives as the CSS max-height cap; on
    // coarse pointers the sheet spans the message column.
    const host=row.parentNode || document.getElementById('messages');
    const anchor=opts.after || row;
    if(anchor.after) anchor.after(panel); else host.appendChild(panel);
    panel.scrollIntoView({block:'nearest', behavior:'smooth'});
    // Tap anywhere outside dismisses; reopening re-opens (siblings are
    // removed at the top of openGroupPicker).
    const dismiss=ev=>{
      if(!panel.contains(ev.target)){ panel.remove(); document.removeEventListener('pointerdown',dismiss,true); }
    };
    document.addEventListener('pointerdown',dismiss,true);
  };
  if(_toolGroupsCache){ doOpen(); return; }
  api('GET','/tools/groups').then(j=>{
    _toolGroupsCache=Array.isArray(j.groups)?j.groups:[];
    doOpen();
  }).catch(()=>{ toast(t('markLoadErr'),true); });
}

async function submitCorrection(row, btn, auditId, group, panel, saveEl, opts){
  saveEl.disabled=true; saveEl.textContent='…';
  try{
    const res=await api('POST','/chat/tool-correction',{audit_id:auditId, expected_group:group});
    panel.remove();
    if(res && res.noop){
      // Same-group "correction" is a no-op (BUG-5): the picked group already
      // matches the tool's own group — tell the user, don't mark as fixed.
      toast(t('corrNoop'));
      return;
    }
    btn.classList.add('marked'); btn.title=t('markDone');
    // A correction is the opposite of a confirmation — drop the up thumb's
    // active look too (backend clears confirmed_at the same way).
    const up=row.querySelector('.fb-up');
    if(up){ up.classList.remove('active'); up.title=t('markConfirm'); }
    if(typeof opts?.onOk==='function') opts.onOk();
  } catch(e){
    if(e && e.message && e.message.startsWith('HTTP ')) toast(t('markErr')+': '+e.message.slice(5), true);
    else toast(t('markErr'), true);
  }
  // Non-success leaves the picker open so the user can retry in place.
  saveEl.disabled=false; saveEl.textContent=t('markSave');
}

function genRetryText(reason){
  if(reason==='tool_leak') return t('genRetryLeak');
  if(reason==='tools_escalated') return t('genRetryEscalate');
  return t('genRetryLabel'); // overflow / empty / unknown
}
function showGenRetry(row, reason){
  if(row && row.isConnected){
    // Retry often lands right after a tool end (✓ state) — revive the pill
    // so the retry label + spinner actually replace the stale "done" look.
    resetPill(row);
    row.querySelector('.tlab').textContent=genRetryText(reason);
    scrollEnd(false);
    return row;
  }
  row=document.createElement('div'); row.className='tool-status';
  row.innerHTML='<span class="tspin"></span><span class="tlab"></span>';
  placeRow(row);
  row.querySelector('.tlab').textContent=genRetryText(reason);
  scrollEnd(false);
  return row;
}
function withStreamCaret(html){
  // Place the blinking caret inline at the very end of the last block —
  // appending after innerHTML would drop it onto its own line.
  const CLOSERS=['</p>','</li>','</h1>','</h2>','</h3>','</blockquote>','</pre>','</ol>','</ul>','</div>'];
  let best=-1;
  for(const c of CLOSERS){ const i=html.lastIndexOf(c); if(i>best) best=i; }
  return best<0 ? html+'<span class="stream-caret"></span>' : html.slice(0,best)+'<span class="stream-caret"></span>'+html.slice(best);
}

const WELCOME_CHIPS = {
  tr:['Son e-postalarımı özetle','Bu haftaki etkinliklerim','Yarın için görev oluştur',
      'Görevlerimi listele','Notları listele','Yeni not oluştur','Bugün hava nasıl?',
      'Yeni etkinlik oluştur','E-posta gönder'],
  en:['Summarize my recent emails','My events this week','Create a task for tomorrow',
      'List my tasks','List my notes','Create a note',"How's the weather today?",
      'Create calendar event','Send an email']
};

let _chipOrigin = false;
let _syncing = false;   // guards against overlapping auto-sync runs
let _autoSync = null;   // bound in init; called after settings save too
let _serverMode = '';   // 'only-server' | 'only-phone' | '' (web)
function chipSend(el){
  const inp = document.getElementById('msg-input');
  if(!inp) return;
  inp.value = el.textContent;
  _chipOrigin = true;            // consumed by sendMsg -> request.origin
  sendMsg();
}

function shuffleChips(list){
  // Random layout per render, with anti-clump rules: a chip may not sit
  // next to itself at a lane's loop seam, and lanes may not start with
  // the same chip stacked. Retry-shuffle beats clever patching here.
  for(let i=0;i<60;i++){
    const l=[...list];
    for(let j=l.length-1;j>0;j--){ const k=Math.floor(Math.random()*(j+1)); [l[j],l[k]]=[l[k],l[j]]; }
    const mid=Math.ceil(l.length/2);
    const r1=l.slice(0,mid), r2=l.slice(mid);
    if(r1.length>1 && r1[0]===r1[r1.length-1]) continue;
    if(r2.length>1 && r2[0]===r2[r2.length-1]) continue;
    if(r1[0]===r2[0]) continue;
    return [r1,r2];
  }
  const mid=Math.ceil(list.length/2);
  return [list.slice(0,mid), list.slice(mid)];
}
function showWelcome(){
  const list = WELCOME_CHIPS[lang] || WELCOME_CHIPS.en;
  const mk = arr => `<span class="chip-set">${arr.map(c => `<button class="w-chip" onclick="chipSend(this)">${c}</button>`).join('')}</span>`;
  const [a,b] = shuffleChips(list);
  const row1 = mk(a) + mk(a);
  const row2 = mk(b) + mk(b);
  document.getElementById('messages').innerHTML=`<div class="welcome"><div class="w-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">  <g class="outer-wrap"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect></g><g class="inner-wrap"><rect x="9" y="9" width="6" height="6"></rect></g></svg></div><div class="w-title">${t('welcomeTitle')}</div><div class="w-sub">${t('welcomeSub').replace(/\n/g,'<br>')}</div><div class="w-marquee"><div class="chip-track">${row1}</div><div class="chip-track rev">${row2}</div></div></div>`;
  initWelcomeMarquee();
  const welcomeEl = document.querySelector('.welcome');
  if(welcomeEl) welcomeEl.classList.add('welcome-anim');
}
function initWelcomeMarquee(){
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('.w-marquee .chip-track').forEach(track=>{
    if(track._mqCtl) return;
    const ctl={x:0,half:1,vx:0,drag:null,holdUntil:0,suppress:false,
               dir:track.classList.contains('rev')?1:-1,
               speed:track.classList.contains('rev')?20:26};
    track._mqCtl=ctl;
    const wrap=()=>{ const h=ctl.half||1;
      if(ctl.dir>0){ while(ctl.x>=h)ctl.x-=h; while(ctl.x<0)ctl.x+=h; }
      else { while(ctl.x>0)ctl.x-=h; while(ctl.x<=-h)ctl.x+=h; }
    };
    const paint=()=>{ const off=(ctl.dir>0)?(ctl.x-ctl.half):ctl.x; track.style.transform=`translate3d(${off}px,0,0)`; };
    const measure=()=>{ const f=track.firstElementChild;
      const g=f?parseFloat(getComputedStyle(track).gap)||0:0;
      ctl.half=(f?f.offsetWidth+g:(track.scrollWidth/2))||track.scrollWidth||1; wrap(); paint(); };
    requestAnimationFrame(()=>requestAnimationFrame(measure));
    addEventListener('resize',measure,{passive:true});

    track.addEventListener('pointerdown',e=>{
      ctl.drag={lastX:e.clientX,x0:e.clientX,y0:e.clientY,moved:0,v:0,lastT:e.timeStamp};
      try{ track.setPointerCapture(e.pointerId); }catch{}
    });
    track.addEventListener('pointermove',e=>{
      const d=ctl.drag; if(!d) return;
      const dx=e.clientX-d.lastX;
      d.lastX=e.clientX; d.moved+=Math.abs(dx);
      const dt=Math.max(1,e.timeStamp-d.lastT)/1000; d.lastT=e.timeStamp;
      d.v=0.7*d.v+0.3*(dx/dt);
      ctl.x+=dx; wrap(); paint();
    });
    const release=()=>{
      const d=ctl.drag; if(!d) return;
      ctl.vx=d.moved>6?d.v:0;
      ctl.suppress=d.moved>6;
      ctl.holdUntil=performance.now()+450;
      setTimeout(()=>{ctl.suppress=false;},80);
      if(d.moved<=6){
        // setPointerCapture retargets the native click to the track, so the
        // chip's own onclick never fires — resolve the chip manually.
        const chip=document.elementFromPoint(d.x0,d.y0)?.closest('.w-chip');
        ctl.drag=null; ctl.pointerJustEnded=true;
        setTimeout(()=>{ctl.pointerJustEnded=false;},120);
        if(chip) chipSend(chip);
        return;
      }
      ctl.drag=null; ctl.pointerJustEnded=true;
      setTimeout(()=>{ctl.pointerJustEnded=false;},120);
    };
    track.addEventListener('pointerup',release);
    track.addEventListener('pointercancel',release);
    // Block only clicks that follow a pointer gesture (capture may retarget
    // them to the track; drags must not click). Keyboard Enter passes through.
    track.addEventListener('click',e=>{
      if(ctl.pointerJustEnded){ e.stopPropagation(); e.preventDefault(); }
    },true);

    let last=performance.now();
    (function frame(now){
      if(!track.isConnected){ removeEventListener('resize',measure); return; }
      const dt=Math.min(50,now-last)/1000; last=now;
      if(!ctl.drag && !reduce && !document.body.classList.contains('settings-open') && !document.hidden && now>=ctl.holdUntil && !document.documentElement.classList.contains('effects-lite')){
        ctl.x+=ctl.dir*ctl.speed*dt;
        if(Math.abs(ctl.vx)>2){ ctl.x+=ctl.vx*dt; ctl.vx*=Math.exp(-3*dt); }
        wrap(); paint();
      }
      requestAnimationFrame(frame);
    })(last);
  });
}
function showWelcomeMsg(){ document.getElementById('messages').innerHTML=''; }
function clearMsgs(){ document.getElementById('messages').innerHTML=''; }

// ── Modals & Actions ────────────────────────────────────────────────────────────
function showConfirmModal(action){
  pendingAction=action; const fields=document.getElementById('m-fields'), btn=document.getElementById('m-confirm'), warn=document.getElementById('m-warn'), iconBox=document.getElementById('m-icon');
  const mailSvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>`;
  const trashSvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`;
  const alertSvg = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;

  if(action.tool==='send_email'){
    iconBox.innerHTML=mailSvg; document.getElementById('m-title').textContent=t('emailConfirm');
    fields.innerHTML=mInput(t('emailTo'), action.params.to||'', 'to') + mInput(t('emailSubj'), action.params.subject||'', 'subject') + mInput(t('emailBody'), action.params.body||'', 'body', true)
      + (action.params.cc ? mInput(t('emailCc'), action.params.cc||'', 'cc') : '')
      + (action.params.bcc ? mInput(t('emailBcc'), action.params.bcc||'', 'bcc') : '');
    warn.style.display='flex'; warn.innerHTML=`${alertSvg} <span>${t('warnEmail')}</span>`; btn.textContent=t('confirm'); btn.className='modal-confirm';
  } else if(action.tool==='delete_calendar_event'){
    iconBox.innerHTML=trashSvg; document.getElementById('m-title').textContent=t('delConfirm');
    fields.innerHTML=mField(t('delEventName'), action.params.summary||''); warn.style.display='flex'; warn.innerHTML=`${alertSvg} <span>${t('warnDel')}</span>`; btn.textContent=t('confirmDel'); btn.className='modal-confirm danger';
  } else if(action.tool==='delete_session'){
    iconBox.innerHTML=trashSvg; document.getElementById('m-title').textContent=t('chatDelConfirm');
    fields.innerHTML=mField(t('chatDelName'), action.params.name||''); warn.style.display='flex'; warn.innerHTML=`${alertSvg} <span>${t('warnChatDel')}</span>`; btn.textContent=t('confirmDel'); btn.className='modal-confirm danger';
  } else if(action.tool==='delete_memory'){
    iconBox.innerHTML=trashSvg; document.getElementById('m-title').textContent=t('memDelConfirm');
    fields.innerHTML=mField(t('memDelContent'), action.params.content||''); warn.style.display='flex'; warn.innerHTML=`${alertSvg} <span>${t('warnMemDel')}</span>`; btn.textContent=t('confirmDel'); btn.className='modal-confirm danger';
  } else if(action.tool==='update_calendar_event'){
    iconBox.innerHTML=alertSvg; document.getElementById('m-title').textContent=t('updateEventConfirm');
    let previewHtml = '';
    if(action.preview) {
      const items = action.preview.split('; ');
      previewHtml = `<div class="modal-field"><label>Eşleşen etkinlikler (${items.length})</label><div class="val" style="font-size:12px;max-height:80px;overflow-y:auto">${items.map(p => esc(p)).join('<br>')}</div></div>`;
    }
    fields.innerHTML=previewHtml
      + mInput(t('delEventName'), action.params.summary||'', 'summary')
      + mInput(t('eventNewSummary'), action.params.new_summary||'', 'new_summary')
      + mInput(t('eventNewTime'), action.params.new_start_time||'', 'new_start_time')
      + mInput(t('eventNewDur'), action.params.new_duration_minutes||'', 'new_duration_minutes');
    warn.style.display='flex'; warn.innerHTML=`${alertSvg} <span>${t('warnDel')}</span>`; btn.textContent=t('confirmAction'); btn.className='modal-confirm';
  } else if(action.tool==='delete_note'){
    iconBox.innerHTML=trashSvg; document.getElementById('m-title').textContent=t('noteDelConfirm');
    let previewHtml = action.preview ? `<div class="modal-field"><label>${t('noteName')}</label><div class="val" style="font-weight:600">${esc(action.preview)}</div></div>` : '';
    fields.innerHTML=previewHtml + mField(t('noteId'), action.params.note_id||''); warn.style.display='flex'; warn.innerHTML=`${alertSvg} <span>${t('warnDel')}</span>`; btn.textContent=t('confirmDel'); btn.className='modal-confirm danger';
  } else if(action.tool==='complete_task'){
    iconBox.innerHTML=alertSvg; document.getElementById('m-title').textContent=t('taskDoneConfirm');
    let previewHtml = action.preview ? `<div class="modal-field"><label>${t('taskName')}</label><div class="val" style="font-weight:600">${esc(action.preview)}</div></div>` : '';
    fields.innerHTML=previewHtml + mField(t('taskUid'), action.params.uid||''); warn.style.display='flex'; warn.innerHTML=`${alertSvg} <span>${t('warnDel')}</span>`; btn.textContent=t('confirmAction'); btn.className='modal-confirm';
  } else if(action.tool==='delete_task'){
    iconBox.innerHTML=trashSvg; document.getElementById('m-title').textContent=t('taskDelConfirm');
    let previewHtml = action.preview ? `<div class="modal-field"><label>${t('taskName')}</label><div class="val" style="font-weight:600">${esc(action.preview)}</div></div>` : '';
    fields.innerHTML=previewHtml + mField(t('taskUid'), action.params.uid||''); warn.style.display='flex'; warn.innerHTML=`${alertSvg} <span>${t('warnDel')}</span>`; btn.textContent=t('confirmDel'); btn.className='modal-confirm danger';
  } else {
    iconBox.innerHTML=alertSvg; document.getElementById('m-title').textContent=action.tool||'Confirm';
    fields.innerHTML=Object.entries(action.params||{}).map(([k,v])=>mField(k, String(v))).join('');
    warn.style.display='flex'; warn.innerHTML=`${alertSvg} <span>${t('warnDel')}</span>`; btn.textContent=t('confirmAction'); btn.className='modal-confirm';
  }
  document.getElementById('confirm-modal').classList.add('open');
}

function mField(label, value){ return `<div class="modal-field"><label>${esc(label)}</label><div class="val">${esc(value)}</div></div>`; }
function mInput(label, value, pkey, multiline){
  if(multiline) return `<div class="modal-field"><label>${esc(label)}</label><textarea class="val-input" data-p="${esc(pkey)}" rows="3">${esc(value)}</textarea></div>`;
  return `<div class="modal-field"><label>${esc(label)}</label><input class="val-input" data-p="${esc(pkey)}" value="${esc(value)}"></div>`;
}
function cancelAction(){ document.getElementById('confirm-modal').classList.remove('open'); pendingAction=null; }

async function confirmAction(){
  if(!pendingAction) return; document.getElementById('confirm-modal').classList.remove('open');
  const tool = pendingAction.tool, params = pendingAction.params;
  document.querySelectorAll('#m-fields .val-input').forEach(inp=>{ params[inp.dataset.p]=inp.value; });
  pendingAction=null;
  if(tool === 'delete_session') {
    try { await api('DELETE','/chat/history?session_id='+encodeURIComponent(params.sid));
      sessionList=sessionList.filter(s=>s.session_id!==params.sid);
      if(currentSid===params.sid){ currentSid=null; clearMsgs(); showWelcome(); } renderSessions(sessionList, false);
    } catch { toast(t('delErr'),true); } return;
  }
  if(tool === 'delete_memory') {
    try { const uid=config.username||'default'; await api('DELETE', `/chat/memories?user_id=${encodeURIComponent(uid)}&id=${encodeURIComponent(params.id)}`); await loadMem(); } catch { toast(t('connErr'),true); } return;
  }
  showTyping(); setLoading(true);
  try{
    const d=await api('POST','/chat/execute',{ session_id:currentSid, user_id:config.username||'default', tool:tool, params:params });
    hideTyping(); addMsg('assistant',d.reply); await loadSessions(false); refreshLastState();
  } catch{ hideTyping(); addMsg('assistant','\u26A0\uFE0F '+t('connErr')); toast(t('connErr'),true); } finally{ setLoading(false); }
}

// ── Memory Panel ────────────────────────────────────────────────────────────────
function setMemView(open){
  memOpen = !!open;
  const chatsLabel = document.getElementById('sb-chats-label');
  const searchEl = document.getElementById('sb-search');
  const sessListEl = document.getElementById('session-list');
  const memHeadEl = document.getElementById('sb-mem-head');
  const memListEl = document.getElementById('sidebar-mem-list');
  const memBtnEl = document.getElementById('mem-toggle-btn');
  sessListEl.classList.toggle('hidden', memOpen);
  if(chatsLabel) chatsLabel.style.display = memOpen ? 'none' : '';
  if(searchEl) searchEl.classList.remove('open');
  if(memOpen){
    memHeadEl.style.display = 'flex'; memListEl.style.display = 'flex'; memBtnEl.classList.add('active'); loadMem();
  } else {
    memHeadEl.style.display = 'none'; memListEl.style.display = 'none'; memBtnEl.classList.remove('active');
  }
}
function toggleMem(){ setMemView(!memOpen); }
function closeMem(){ if(memOpen) setMemView(false); }

async function loadMem(){
  const list=document.getElementById('sidebar-mem-list'); list.innerHTML=`<div class="mem-empty">${t('loading')}</div>`;
  try{
    const uid=config.username||'default'; const d=await api('GET',`/chat/memories?user_id=${encodeURIComponent(uid)}`); const mems=d.memories||[];
    if(!mems.length){
      list.innerHTML=`<div class="mem-empty"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--surface3)" stroke-width="2" stroke-linecap="round" style="margin-bottom:8px"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg><br>${t('noMem')}<br><span style="font-size:11px;color:var(--text4);display:block;margin-top:4px">${t('noMemNote')}</span></div>`;
      return;
    }
    list.innerHTML=mems.map(m=>{
      const cat=m.category||'general', mid=m.id || m.content, imp=m.importance||5;
      return `<div class="mem-card" data-imp="${imp}"><div class="mem-cat cat-${esc(cat)}">${esc(cat)}</div><div class="mem-content">${esc(m.content)}</div><div class="mem-date">${relTime(m.created_at)} · importance: ${imp}</div><button class="mem-del-btn" data-mid="${esc(String(mid))}" data-content="${esc(m.content)}" aria-label="${t('del')}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button></div>`;
    }).join('');
    list.querySelectorAll('.mem-del-btn').forEach(btn=>{
      btn.addEventListener('click', ()=> triggerDelMemory(btn.dataset.mid, btn.dataset.content));
    });
  } catch{ list.innerHTML=`<div class="mem-empty">${t('connErr')}</div>`; }
}
function triggerDelMemory(id, content) { showConfirmModal({ tool: 'delete_memory', params: { id: id, content: content } }); }

// ── Settings Panel ──────────────────────────────────────────────────────────────
let _settingsData = {};

const SETTINGS_GROUPS = {
  'General':    ['UI_LANGUAGE'],
  'Model':      ['LLM_BACKEND','LLM_MODEL'],
  'Generation': ['LLM_TEMPERATURE','LLM_NUM_CTX','LLM_MAX_OUTPUT_TOKENS'],
  'Chat':       ['HISTORY_LIMIT','MEMORY_LIMIT','LLM_TITLE_ENRICHMENT'],
  'Voice':      ['TTS_VOICE','TTS_ENGINE','STT_ENGINE','AUTO_SEND_ON_VOICE','AUTO_TTS_ON_VOICE'],
  'Personal':   ['ASSISTANT_USER','MAIL_PROVIDER','DEFAULT_CITY'],
};

const ADVANCED_KEYS = new Set([
  'LLM_TOP_P','LLM_TOP_K','LLM_KEEP_ALIVE','SUMMARY_BATCH_SIZE',
  'MEMORY_SIMILARITY_THRESHOLD','CONVERSATION_RETENTION_DAYS',
  'MEMORY_RETENTION_DAYS','INTENT_LLM_FALLBACK',
]);

const HIDDEN_KEYS = new Set(['LLM_REASONING_EFFORT']);

const SECTION_LABELS = {
  tr:{'Appearance':'Görünüm','General':'Genel','Generation':'Üretim','Model':'Model & Motor','Chat':'Sohbet','Voice':'Ses','Personal':'Kişisel','Other':'Diğer','Advanced':'Gelişmiş Ayarlar','Telefon':'Telefon','Sunucu':'Sunucu','Zeka':'Zeka','Üretim':'Üretim','Sohbet':'Sohbet','Hava':'Hava','Notlar':'Notlar','Ses':'Ses','Uygulama':'Uygulama','Senkron':'Senkron','Bağlantı':'Bağlantı','Kişisel':'Kişisel'},
  en:{'Appearance':'Appearance','General':'General','Generation':'Generation','Model':'Model & Engine','Chat':'Chat','Voice':'Voice','Personal':'Personal','Other':'Other','Advanced':'Advanced Settings','Telefon':'Phone','Sunucu':'Server','Zeka':'Intelligence','Üretim':'Generation','Sohbet':'Chat','Hava':'Weather','Notlar':'Notes','Ses':'Voice','Uygulama':'App','Senkron':'Sync','Bağlantı':'Connection','Kişisel':'Personal'},
};

// Desktop chip rail order; 'Appearance' maps to the always-on UI settings row.
const SETTING_CHIP_ORDER = ['Appearance','General','Model','Generation','Chat','Voice','Personal','Advanced'];

function bindSettingsChips(){
  // UI settings live OUTSIDE the fetch-driven form (they are always visible);
  // chips simply link to every section, hidden entirely when little to jump to.
  const wrap=document.getElementById('settings-chips');
  const body=document.querySelector('.settings-body');
  if(!wrap||!body) return;
  wrap.innerHTML='';
  const anchors=SETTING_CHIP_ORDER.map(key=>{
    const el = key==='Appearance' ? document.getElementById('settings-appearance')
      : document.querySelector('#settings-form [data-sec="'+key+'"]');
    return el ? {key, el} : null;
  }).filter(Boolean);
  wrap.classList.toggle('min', anchors.length<2);
  const chips=[];
  const setActive=(b)=>{ chips.forEach(x=>x.classList.toggle('active',x===b)); };
  for(const a of anchors){
    const b=document.createElement('button');
    b.className='set-chip'; b.type='button';
    b.textContent = a.key==='Appearance' ? _sectionLabel('Appearance') : _sectionLabel(a.key);
    b.onclick=()=>{
      const br=body.getBoundingClientRect(), r=a.el.getBoundingClientRect();
      body.scrollTop += r.top-br.top-10;
      setActive(b);
    };
    chips.push(b); wrap.appendChild(b);
  }
  if(!anchors.length) return;
  const measure=()=>anchors.forEach(a=>{ const br=body.getBoundingClientRect(); a.absY=a.el.getBoundingClientRect().top-br.top+body.scrollTop; });
  measure();
  window.addEventListener('resize',measure,{passive:true});
  let ticking=false;
  const tick=()=>{
    ticking=false;
    const st=body.scrollTop;
    let cur=anchors[0];
    for(let i=0;i<anchors.length;i++){ if(anchors[i].absY<=st+28) cur=anchors[i]; else break; }
    chips.forEach((x,i)=>x.classList.toggle('active', i===anchors.indexOf(cur)));
  };
  body.addEventListener('scroll',()=>{ if(!ticking){ ticking=true; requestAnimationFrame(tick); } },{passive:true});
  tick();
}

const SETTING_HINTS = {
  LLM_TOP_P: {
    tr:'Çıktının çeşitliliğini ayarlayan olasılık eşiği. Tekrarlayan/karmaşık çıktı görürsen düşür (örn. 0.7). Yüksek = daha çeşitli. Varsayılan: 0.85',
    en:'Probability threshold for output diversity. Lower it (e.g. 0.7) if output repeats or garbles. Higher = more varied. Default: 0.85',
  },
  LLM_TOP_K: {
    tr:'Her adımda değerlendirilen en iyi token sayısı. Küçük = daha odaklı, büyük = daha çeşitli. Varsayılan: 40',
    en:'Number of best tokens considered at each step. Smaller = more focused, larger = more varied. Default: 40',
  },
  LLM_KEEP_ALIVE: {
    tr:'Modelin bellekte ne kadar süre yüklü tutulacağı. RAM azsa düşür (örn. 1h); hızlı yanıt istersen artır (örn. 12h). Varsayılan: 4h',
    en:'How long the model stays loaded in memory. Lower (e.g. 1h) if RAM is tight; raise (e.g. 12h) for faster replies. Default: 4h',
  },
  SUMMARY_BATCH_SIZE: {
    tr:'Sohbet özetinin kaç mesajda bir yenileneceği. Küçük = daha güncel ama daha çok işlem; büyük = daha az güncel. Varsayılan: 5',
    en:'How often (in messages) the conversation summary refreshes. Smaller = more up-to-date but more processing. Default: 5',
  },
  MEMORY_SIMILARITY_THRESHOLD: {
    tr:'Bir hafıza kartının konuşmaya ne kadar benzeşmesi gerektiği. Yüksek = daha az ama isabetli eşleşme; düşük = daha çok ama gürültülü. Varsayılan: 0.68',
    en:'How similar a memory card must be to be included. Higher = fewer, more relevant matches; lower = more, noisier. Default: 0.68',
  },
  CONVERSATION_RETENTION_DAYS: {
    tr:'Sohbetlerin otomatik silinmeden önce saklanacağı gün sayısı. 0 = silme yok. Yalnızca otomatik temizlik istiyorsan değiştir. Varsayılan: 0',
    en:'Days conversations are kept before auto-deletion. 0 = never delete. Only change for automatic cleanup. Default: 0',
  },
  MEMORY_RETENTION_DAYS: {
    tr:'Hafıza kartlarının otomatik silinmeden önce saklanacağı gün sayısı. 0 = silme yok. Varsayılan: 0',
    en:'Days memory cards are kept before auto-deletion. 0 = never delete. Default: 0',
  },
  INTENT_LLM_FALLBACK: {
    tr:'Niyet tespitinde emin olunamayınca LLM\'e de danışılır. Daha isabetli ama bazı yanıtlar +15 sn gecikebilir. Varsayılan: Kapalı',
    en:'Asks the LLM when intent detection is uncertain. More accurate but some replies may take +15s. Default: Off',
  },
};

function _sectionLabel(s){ return (SECTION_LABELS[lang] || SECTION_LABELS.en)[s] || s; }
function _settingHint(key){
  const h = SETTING_HINTS[key];
  return h ? (h[lang] || h.tr || h.en) : '';
}

function _settingLabel(entry) {
  const lbl = entry.label || {};
  return lbl[lang] || lbl.tr || lbl.en || '';
}

function _renderSetting(key, entry, advanced) {
  const val = entry.value;
  const type = entry.type;
  // Native schema sends options as "a|b|c"; web server sends an array of
  // {value,label}. Normalize both to {value,label}[] here.
  let optsArr = entry.options;
  if (typeof optsArr === 'string') {
    optsArr = '|'.repeat(0) + optsArr; // keep parity
    optsArr = optsArr.split('|').filter(Boolean).map(o => ({value:o, label:{tr:o, en:o}}));
  } else if (Array.isArray(optsArr)) {
    optsArr = optsArr.map(o => typeof o === 'string' ? {value:o, label:{tr:o, en:o}} : o);
  } else {
    optsArr = [];
  }
  const label = _settingLabel(entry);
  const dl = entry.desc || {};
  const descText = dl[lang] || dl.tr || dl.en || '';
  const descDiv = (!advanced && descText) ? `<div class="setting-desc">${esc(descText)}</div>` : '';
  const infoBtn = advanced ? `<button class="info-btn" id="ib-${key}" onclick="toggleSettingInfo('${key}')" aria-label="?">\u24D8</button>` : '';
  const hintDiv = advanced ? `<div class="setting-hint" id="hi-${key}" style="display:none">${esc(_settingHint(key))}</div>` : '';

  if (type === 'select' && optsArr.length === 2 &&
      optsArr.some(o => o.value === 'on') && optsArr.some(o => o.value === 'off')) {
    const checked = val === 'on';
    const row = advanced
      ? `<div class="setting-label"><span class="label-wrap"><span>${esc(label || key)}</span>${infoBtn}</span><label class="switch"><input type="checkbox" id="si-${key}" ${checked ? 'checked' : ''} onchange="this.dataset.val=this.checked?'on':'off'"><span class="track"></span></label></div>`
      : `<div class="setting-label"><span>${esc(label || key)}</span><label class="switch"><input type="checkbox" id="si-${key}" ${checked ? 'checked' : ''} onchange="this.dataset.val=this.checked?'on':'off'"><span class="track"></span></label></div>`;
    return `<div class="setting-item${advanced ? ' advanced' : ''}">${row}${hintDiv}${descDiv}</div>`;
  }

  if (type === 'select' && optsArr.length) {
    let opts = '';
    for (const opt of optsArr) {
      const olbl = _settingLabel(opt);
      opts += `<option value="${esc(opt.value)}" ${opt.value === val ? 'selected' : ''}>${esc(olbl)}</option>`;
    }
    const row = advanced
      ? `<div class="setting-label"><span class="label-wrap"><span>${esc(label || key)}</span>${infoBtn}</span></div>`
      : `<div class="setting-label"><span>${esc(label || key)}</span></div>`;
    return `<div class="setting-item${advanced ? ' advanced' : ''}">${row}<select class="setting-input" id="si-${key}">${opts}</select>${hintDiv}${descDiv}</div>`;
  } else if (type === 'float' || type === 'int') {
    const min = entry.min ?? 0;
    const max = entry.max ?? 100;
    const step = entry.step ?? 1;
    const row = advanced
      ? `<div class="setting-label"><span class="label-wrap"><span>${esc(label || key)}</span>${infoBtn}</span><span class="val-display" id="sv-${key}">${esc(val)}</span></div>`
      : `<div class="setting-label"><span>${esc(label || key)}</span><span class="val-display" id="sv-${key}">${esc(val)}</span></div>`;
    return `<div class="setting-item${advanced ? ' advanced' : ''}">${row}<input type="range" class="setting-input" id="si-${key}" min="${min}" max="${max}" step="${step}" value="${esc(val)}" oninput="document.getElementById('sv-${key}').textContent=this.value">${hintDiv}${descDiv}</div>`;
  } else {
    const row = advanced
      ? `<div class="setting-label"><span class="label-wrap"><span>${esc(label || key)}</span>${infoBtn}</span></div>`
      : `<div class="setting-label"><span>${esc(label || key)}</span></div>`;
    return `<div class="setting-item${advanced ? ' advanced' : ''}">${row}<input type="text" class="setting-input" style="padding:8px 10px" id="si-${key}" value="${esc(val)}">${hintDiv}${descDiv}</div>`;
  }
}

async function openSettings(){
  document.getElementById('settings-modal').classList.add('open');
  document.body.classList.add('settings-open');
  const form = document.getElementById('settings-form');
  form.innerHTML = `<div style="text-align:center;padding:12px;color:var(--text3)">${t('loading')}</div>`;
  document.getElementById('settings-pane-server').innerHTML = '';
  const notice = document.getElementById('settings-restart-notice');
  notice.style.display = 'none';

  // Sync appearance controls — these are UI-only (localStorage) and render
  // WITHOUT waiting for the backend, so they survive offline / fetch errors.
  document.querySelector('#settings-appearance').innerHTML = `
    <div class="appearance-group">
      <label id="lbl-theme-select"></label>
      <div class="theme-grid" id="theme-grid"></div>
    </div>
    <div class="appearance-group">
      <label id="lbl-lang-select"></label>
      <select class="lang-select" id="lang-select" onchange="applyLang(this.value)">
        <option value="tr">Türkçe</option>
        <option value="en">English</option>
      </select>
    </div>
    <div class="appearance-group">
      <label id="lbl-glass-label"></label>
      <div class="switch-wrap">
        <label class="switch">
          <input type="checkbox" id="glass-toggle" onchange="applyGlass(this.checked)">
          <span class="track"></span>
        </label>
      </div>
    </div>
    <div class="appearance-group">
      <label id="lbl-minimal-label"></label>
      <div class="switch-wrap">
        <label class="switch">
          <input type="checkbox" id="minimal-toggle" onchange="applyMinimal(this.checked)">
          <span class="track"></span>
        </label>
      </div>
      <div class="minimal-desc" id="minimal-desc"></div>
    </div>
    <div class="appearance-group">
      <label id="lbl-amoled-label"></label>
      <div class="switch-wrap">
        <label class="switch">
          <input type="checkbox" id="amoled-toggle" onchange="applyAmoled(this.checked)">
          <span class="track"></span>
        </label>
      </div>
      <div class="minimal-desc" id="amoled-desc"></div>
    </div>
    <div class="appearance-group">
      <label id="lbl-font-label"></label>
      <select class="lang-select" id="font-select" onchange="applyFont(this.value)">
        <option value="dmsans">DM Sans</option>
        <option value="system">Sistem</option>
      </select>
    </div>`;
  document.getElementById('lbl-theme-select').textContent = t('themeLabel');
  document.getElementById('lbl-lang-select').textContent = t('langLabel');
  if(document.getElementById('lbl-amoled-label')) document.getElementById('lbl-amoled-label').textContent = t('amoledLabel');
  if(document.getElementById('amoled-desc')) document.getElementById('amoled-desc').textContent = t('amoledDesc');
  const amoledToggle = document.getElementById('amoled-toggle');
  if(amoledToggle){ amoledToggle.checked = amoled; }
  if(document.getElementById('lbl-font-label')) document.getElementById('lbl-font-label').textContent = t('fontLabel');
  const fontSelect = document.getElementById('font-select');
  if(fontSelect){ fontSelect.value = fontMode; }
  const glassLabel = document.getElementById('lbl-glass-label');
  if(glassLabel) glassLabel.textContent = t('glassLabel');
  const glassToggle = document.getElementById('glass-toggle');
  if(glassToggle){ glassToggle.checked = glass; }
  const minimalLabelEl = document.getElementById('lbl-minimal-label');
  if(minimalLabelEl) minimalLabelEl.textContent = t('minimalLabel');
  const minimalDescEl = document.getElementById('minimal-desc');
  if(minimalDescEl) minimalDescEl.textContent = t('minimalDesc');
  const minimalToggleEl = document.getElementById('minimal-toggle');
  if(minimalToggleEl){ minimalToggleEl.checked = minimal; }
  document.getElementById('lang-select').value = lang;
  renderThemeGrid();

  const tabsEl = document.getElementById('settings-tabs');
  const phoneTab = document.getElementById('tab-phone');
  const serverTab = document.getElementById('tab-server');
  if(phoneTab) phoneTab.textContent = _sectionLabel('Telefon');
  if(serverTab) serverTab.textContent = _sectionLabel('Sunucu');
  const setTabActive = (tab)=>{
    phoneTab.classList.toggle('active', tab==='phone');
    serverTab.classList.toggle('active', tab==='server');
    document.getElementById('settings-pane-phone').hidden = tab!=='phone';
    document.getElementById('settings-pane-server').hidden = tab!=='server';
  };
  if(tabsEl) tabsEl.onclick = (e)=>{
    const b = e.target.closest('.set-tab'); if(!b) return;
    setTabActive(b.dataset.tab);
  };

  try {
    _settingsData = await api('GET', '/config/settings');
    const keySet = new Set(Object.keys(_settingsData));
    let html = '';
    const usedKeys = new Set();

    const renderGroup = (title, keys, advanced) => {
      const sectionKeys = keys.filter(k => keySet.has(k) && !HIDDEN_KEYS.has(k) &&
        (advanced ? ADVANCED_KEYS.has(k) : !ADVANCED_KEYS.has(k)));
      if (!sectionKeys.length) return '';
      const items = sectionKeys.map(k => { usedKeys.add(k); return _renderSetting(k, _settingsData[k], advanced); }).join('');
      if (advanced) {
        return `<div class="settings-section" data-sec="Advanced"><div class="settings-section-title adv-toggle" id="adv-toggle" onclick="toggleAdvanced()"><span class="adv-chev">▸</span><span id="lbl-advanced">${_sectionLabel('Advanced')}</span></div><div class="settings-section-inner adv-inner" id="advanced-inner" style="display:none">${items}</div></div>`;
      }
      return `<div class="settings-section" data-sec="${title}"><div class="settings-section-title">${_sectionLabel(title)}</div><div class="settings-section-inner">${items}</div></div>`;
    };

    // SPLIT: native (this build) returns groups prefixed "Telefon ·" / "Sunucu ·".
    // Web server returns legacy flat groups; detect which pane a key belongs to.
    // Browser never shows the phone/server tabs regardless of schema.
    const groupOf = (k)=> (_settingsData[k] && _settingsData[k].group) || '';
    const isPhoneGroup = (g)=> g.indexOf('Telefon') === 0;
    const isServerGroup = (g)=> g.indexOf('Sunucu') === 0;

    const phoneKeys = _NATIVE ? Object.keys(_settingsData).filter(k => {
      const g = groupOf(k);
      if (isServerGroup(g)) return false;
      if (isPhoneGroup(g)) return true;
      return false; // unknown server-origin keys stay out unless explicitly assigned
    }) : [];
    const serverKeys = _NATIVE ? Object.keys(_settingsData).filter(k => isServerGroup(groupOf(k))) : [];

    // Build distinct section groups by the group label for both panes.
    const byGroup = (keys)=> {
      const map = {};
      for (const k of keys) {
        let g = groupOf(k).replace(/^(Telefon|Sunucu) · /, '');
        map[g] = map[g] || [];
        map[g].push(k);
      }
      return map;
    };

    const renderFromGroups = (groups)=>{
      let h = '';
      for (const g in groups) {
        const keys = groups[g];
        const items = keys.filter(k => !usedKeys.has(k)).map(k => { usedKeys.add(k); return _renderSetting(k, _settingsData[k], false); }).join('');
        if (!items) continue;
        h += `<div class="settings-section" data-sec="${_sectionLabel(g)}"><div class="settings-section-title">${_sectionLabel(g)}</div><div class="settings-section-inner">${items}</div></div>`;
      }
      return h;
    };

    if (phoneKeys.length || serverKeys.length) {
      // Native (Telefon/Sunucu) schema
      html = renderFromGroups(byGroup(phoneKeys));
      document.getElementById('settings-form').innerHTML = html;
      const serverHtml = renderFromGroups(byGroup(serverKeys));
      document.getElementById('settings-pane-server').innerHTML = serverHtml;
      enhanceAllSelects(form);
      enhanceAllSelects(document.getElementById('settings-pane-server'));
      if (tabsEl) tabsEl.hidden = !serverKeys.length;
      setTabActive('phone');
    } else {
      // Legacy web server schema (single pane, no tabs)
      tabsEl.hidden = true;
      document.getElementById('settings-pane-server').hidden = true;
      document.getElementById('settings-pane-phone').hidden = false;
      for (const [sectionLabel, keys] of Object.entries(SETTINGS_GROUPS)) {
        html += renderGroup(sectionLabel, keys, false);
      }
      html += renderGroup('Advanced', Object.keys(_settingsData), true);
      const remaining = Object.keys(_settingsData).filter(k => !usedKeys.has(k) && !HIDDEN_KEYS.has(k) && !ADVANCED_KEYS.has(k));
      if (remaining.length) {
        const items = remaining.map(k => _renderSetting(k, _settingsData[k], false)).join('');
        html += `<div class="settings-section"><div class="settings-section-title">${_sectionLabel('Other')}</div><div class="settings-section-inner">${items}</div></div>`;
      }
      html += serverSectionHtml();
      form.innerHTML = html;
      enhanceAllSelects(form);
    }
    bindSettingsChips();
  } catch {
    form.innerHTML = `<div style="text-align:center;padding:12px;color:var(--danger)">${t('connErr')}</div>`;
    bindSettingsChips();
  }
}

function toggleAdvanced(){
  const inner = document.getElementById('advanced-inner');
  const toggle = document.getElementById('adv-toggle');
  if(!inner) return;
  const show = inner.style.display === 'none';
  inner.style.display = show ? '' : 'none';
  if(toggle) toggle.classList.toggle('open', show);
}

function toggleSettingInfo(key){
  const hi = document.getElementById('hi-' + key);
  if(!hi) return;
  const show = hi.style.display === 'none';
  hi.style.display = show ? '' : 'none';
  const ib = document.getElementById('ib-' + key);
  if(ib) ib.classList.toggle('on', show);
}

function serverSectionHtml(){
  const url = localStorage.getItem('ps_server_url') || (window.location.origin.startsWith('http') ? window.location.origin : '');
  const key = localStorage.getItem('ps_api_key') || '';
  return `
    <div class="settings-section" data-sec="Sunucu">
      <div class="settings-section-title">${_sectionLabel('Sunucu')}</div>
      <div class="settings-section-inner">
        <div class="setting-item">
          <div class="setting-label"><span>${esc(t('setServerUrl'))}</span></div>
          <div class="setting-desc">${esc(t('setServerUrlDesc'))}</div>
          <input type="text" class="setting-input" style="padding:8px 10px" id="si-ps_server_url" maxlength="200" value="${esc(url)}">
        </div>
        <div class="setting-item">
          <div class="setting-label"><span>${esc(t('setApiKeyLabel'))}</span></div>
          <div class="setting-desc">${esc(t('setApiKeyDesc'))}</div>
          <input type="password" class="setting-input" style="padding:8px 10px" id="si-ps_api_key" maxlength="200" autocomplete="off" value="${esc(key)}" placeholder="${esc(t('setApiKeyPh'))}">
        </div>
      </div>
    </div>`;
}

function closeSettings(){ document.getElementById('settings-modal').classList.remove('open'); document.body.classList.remove('settings-open'); }
document.addEventListener('keydown', (e)=>{
  if(e.key==='Escape'){
    const cm=document.getElementById('confirm-modal');
    if(cm&&cm.classList.contains('open')){ cancelAction(); return; }
    const sm=document.getElementById('settings-modal');
    if(sm&&sm.classList.contains('open')) closeSettings();
  }
});

async function saveSettings(){
  const values = {};
  for (const key of Object.keys(_settingsData)) {
    const el = document.getElementById('si-' + key);
    if (el) values[key] = el.type === 'checkbox' ? (el.dataset.val || (el.checked ? 'on' : 'off')) : el.value;
  }
  if(!_NATIVE){
    const urlEl = document.getElementById('si-ps_server_url');
    if(urlEl){
      const v = urlEl.value.trim();
      if(v) localStorage.setItem('ps_server_url', v);
    }
    const keyEl = document.getElementById('si-ps_api_key');
    if(keyEl) setApiKey(keyEl.value.trim());
  }

  try {
    const result = await api('PATCH', '/config/settings', { values });
    toast(t('settingsSaved'));
    if (result.restart_required && result.restart_required.length > 0) {
      document.getElementById('settings-restart-notice').style.display = 'block';
    }
    // Refresh config + settings data so TTS/STT engine changes take effect immediately
    try {
      config = await api('GET', '/config');
      const s = await api('GET', '/config/settings');
      if(s){
        Object.assign(_settingsData, s);
        _serverMode = (s.SYNC_MODE && s.SYNC_MODE.value) ? s.SYNC_MODE.value : _serverMode;
        refreshServerStatus();
        if(_serverMode==='only-server') _nativeChatRestore();
      }
      if(_autoSync) setTimeout(_autoSync, 800);
    } catch {}
    setTimeout(closeSettings, 800);
  } catch {
    toast(t('connErr'), true);
  }
}

// ── Onboarding (first-run setup wizard) ─────────────────────────────────────────
// Native: welcome → permissions → personal → server → model status → tour.
// Browser: permissions (native-only) and model status (native-only) are skipped.
const OB_STEPS = _NATIVE ? ['s1','s2','s3','s6','s4','s5'] : ['s1','s3','s6','s5'];
let _ob = { step: 0, perms: { calendar:false, microphone:false, location:false }, modelUrl: '' };

function obIcon(name){
  const I = {
    wave:'<path d="M5 12h14M12 5v14"></path>',
    perm:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>',
    user:'<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle>',
    chip:'<rect x="4" y="4" width="16" height="16" rx="2"></rect><rect x="9" y="9" width="6" height="6"></rect>',
    tour:'<circle cx="12" cy="12" r="10"></circle><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"></path><path d="M12 17h.01"></path>',
    server:'<rect x="2" y="2" width="20" height="8" rx="2"></rect><rect x="2" y="14" width="20" height="8" rx="2"></rect><path d="M6 6h.01M6 18h.01"></path>',
  };
  return `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${I[name]||''}</svg>`;
}

function obPermIcon(kind, granted){
  const g = granted ? ' granted' : '';
  return `<div class="ob-perm-icon${g}"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${granted?'<path d="M5 12l5 5L20 7"></path>':'<circle cx="12" cy="12" r="10"></circle>'}</svg></div>`;
}

function obRenderDots(){
  const dots = document.getElementById('ob-dots');
  if(!dots) return;
  dots.innerHTML = OB_STEPS.map((_,i)=>`<div class="ob-dot${i===_ob.step?' cur':''}"></div>`).join('');
  const badge = document.getElementById('ob-badge');
  if(badge) badge.textContent = `${_ob.step+1}/${OB_STEPS.length} · ${t('obBadge')}`;
}

async function obNextAction(){
  const btn = document.getElementById('ob-next');
  if(btn) btn.disabled = true;
  try{
    if(_ob.step === OB_STEPS.length - 1){ finishOnboarding(); return; }
    const action = btn && btn.dataset.action;
    if(action === 'server'){
      const url = document.getElementById('ob-surl')?.value.trim();
      const key = document.getElementById('ob-skey')?.value.trim() || '';
      if(_NATIVE){
        const values = {};
        if(url) values.SERVER_URL = url;
        const user = document.getElementById('ob-suser')?.value.trim();
        if(user) values.SERVER_USER = user;
        if(key) values.SERVER_API_KEY = key;
        try{ await api('PATCH','/config/settings',{values}); }catch(e){}
        if(key) setApiKey(key);
        // User just logged in to a server: pull its portable settings to the phone.
        if(url || key){ try{ await _serverSettingsPull(); }catch(e){} }
      } else {
        if(url) localStorage.setItem('ps_server_url', url);
        setApiKey(key);
      }
    }
    if(action === 'save'){
      // persist personal info
      const name = document.getElementById('ob-aname')?.value.trim();
      const city = document.getElementById('ob-city')?.value.trim();
      const values = {};
      if(name) values.ASSISTANT_USER = name;
      if(city) values.DEFAULT_CITY = city;
      if(Object.keys(values).length){
        try{ await api('PATCH','/config/settings',{values}); if(window.config) config = await api('GET','/config'); }catch(e){}
      }
    }
    _ob.step++;
    if(_ob.step < OB_STEPS.length){
      renderOnboarding();
      if(OB_STEPS[_ob.step] === 's4') preloadModelCheck();
    } else {
      finishOnboarding();
    }
  } finally {
    if(btn) btn.disabled = false;
  }
}

function obGoBack(){
  if(_ob.step === 0) return;
  _ob.step--;
  renderOnboarding();
}

async function preloadModelCheck(){
  const statusEl = document.getElementById('ob-model-status');
  if(!statusEl) return;
  if(_NATIVE){
    const s = await P().configGet();
    const c = (k)=>{ const o=s[k]; return o?o.value:''; };
    _ob.modelUrl = c('MODEL_URL') || '';
  }
  if(!_NATIVE) return;
  try{
    const st = await _NATIVE.modelStatus();
    if(st && typeof st === 'object' && (st.loaded === true || st.available === true)){
      statusEl.innerHTML = `<div class="ob-status ok"><span class="ob-status-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12l5 5L20 7"></path></svg></span><span class="ob-status-msg">${esc(t('obModelOk'))}</span></div>`;
    } else {
      statusEl.innerHTML = `
        <div class="ob-status warn"><span class="ob-status-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg></span><span class="ob-status-msg">${esc(t('obModelNone'))}</span></div>
        <div class="ob-hint">${esc(t('obModelHint'))}</div>
        <div style="display:flex;flex-direction:column;gap:8px;margin-top:12px">
          <button class="ob-btn" id="ob-dl-hf" style="width:100%" onclick="obStartModelDl('hf')">${esc(t('obModelDown'))}</button>
          <button class="ob-btn ghost" id="ob-dl-custom" style="width:100%" onclick="obCustomUrlToggle()">${esc(t('obModelDownCustom'))}</button>
          <div id="ob-custom-url-wrap" style="display:none;flex-direction:column;gap:8px">
            <input class="ob-input" id="ob-custom-url" maxlength="500" placeholder="https://sunucu.adresi/model.litertlm" value="${esc(_ob.modelUrl || '')}">
            <button class="ob-btn" style="width:100%" onclick="obStartModelDl('custom')">${esc(t('obModelDownUrl'))}</button>
          </div>
        </div>
        <div id="ob-dl-progress" style="display:none;flex-direction:column;gap:8px;margin-top:12px">
          <div class="progress"><div class="progress-bar" id="ob-dl-bar" style="width:0%"></div></div>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span class="ob-status-msg" id="ob-dl-pct" style="font-size:13px">${esc(t('obModelDownStart'))}</span>
            <button class="ob-btn ghost" style="font-size:12px;padding:7px 12px" onclick="obCancelModelDl()">${esc(t('obModelCancel'))}</button>
          </div>
        </div>`;
    }
  } catch(e){ statusEl.innerHTML = `<div class="ob-status warn"><span class="ob-status-msg">${esc(t('obModelNone'))}</span></div>`; }
}

function obCustomUrlToggle(){
  const wrap = document.getElementById('ob-custom-url-wrap');
  if(!wrap) return;
  if(wrap.style.display === 'flex'){ wrap.style.display = 'none'; return; }
  wrap.style.display = 'flex';
  const inp = document.getElementById('ob-custom-url');
  if(inp) setTimeout(()=>inp.focus(), 50);
}

let _obDlActive = false;

async function obStartModelDl(kind){
  if(_obDlActive) return;
  const wrap = document.getElementById('ob-dl-hf');
  const prev = document.getElementById('ob-dl-custom');
  if(kind === 'custom'){
    const url = document.getElementById('ob-custom-url')?.value.trim();
    if(url){
      try{ await api('PATCH','/config/settings',{values:{MODEL_URL:url}}); }catch(e){}
    }
  }
  try{
    const st = await _NATIVE.modelDownloadStatus();
    const targets = st && Array.isArray(st.targets) ? st.targets : [];
    let target = 'custom';
    if(kind === 'hf') target = 'hf';
    const any = targets.find(x => x.id && x.id.indexOf(kind === 'hf' ? 'hf-' : 'custom') === 0) || targets[targets.length-1];
    if(!any){ if(prev){prev.textContent = t('obModelDownFail');} return; }
    _obDlActive = true;
    wrap.style.display='none';
    prev.style.display='none';
    const prog = document.getElementById('ob-dl-progress');
    prog.style.display='flex';
    prog.style.flexDirection='column';
    const bar = document.getElementById('ob-dl-bar');
    const pctEl = document.getElementById('ob-dl-pct');
    bar.style.width='0%';
    pctEl.textContent = t('obModelDownStart');
    const off = await _NATIVE.addListener('modelProgress', (d)=>{
      if(d && d.state === 'done'){
        pctEl.textContent = t('obModelDownDone');
        bar.style.width='100%';
        obModelDlDone();
      } else if(d && (d.state === 'failed' || d.state === 'cancelled')){
        pctEl.textContent = t('obModelDownFail');
        _obDlActive = false;
        rendDlButtons();
      } else if(d){
        const p = Math.max(0, Math.min(100, Math.round(d.percentage || 0)));
        bar.style.width = p + '%';
        pctEl.textContent = t('obModelPct').replace('%s', d.total>0 ? formatBytes(d.bytes) + ' / ' + formatBytes(d.total) : formatBytes(d.bytes));
      }
    });
    await _NATIVE.startModelDownload({target: any.id});
    setTimeout(async ()=>{ try{ await off; }catch(e){ obModelDlDone(); } }, 600);
  }catch(e){
    _obDlActive = false;
    try{ await _NATIVE.cancelModelDownload(); }catch(_){}
    rendDlButtons();
  }
}

function rendDlButtons(){
  const wrap = document.getElementById('ob-dl-hf');
  const prev = document.getElementById('ob-dl-custom');
  if(wrap) wrap.style.display = '';
  if(prev) prev.style.display = '';
  const urlWrap = document.getElementById('ob-custom-url-wrap');
  if(urlWrap) urlWrap.style.display = 'none';
  const prog = document.getElementById('ob-dl-progress');
  if(prog) prog.style.display = 'none';
}

async function obCancelModelDl(){
  _obDlActive = false;
  try{ await _NATIVE.cancelModelDownload(); }catch(e){}
  rendDlButtons();
}

function obModelDlDone(){
  _obDlActive = false;
  preloadModelCheck();
}

function formatBytes(n){
  if(n===undefined||n===null||isNaN(n)) return '0 B';
  const u=['B','KB','MB','GB','TB']; let i=0;
  while(n>=1024 && i<u.length-1){ n/=1024; i++; }
  return (i===0 ? Math.round(n) : n.toFixed(1)) + ' ' + u[i];
}

function renderOnboarding(){
  const body = document.getElementById('ob-body');
  if(!body) return;
  const back = document.getElementById('ob-back');
  const next = document.getElementById('ob-next');
  if(back) back.style.visibility = _ob.step === 0 ? 'hidden' : 'visible';
  if(back) back.textContent = t('cancel');
  _ob.step = Math.max(0, Math.min(_ob.step, OB_STEPS.length-1));
  obRenderDots();

  const step = OB_STEPS[_ob.step];
  if(step === 's1'){
    body.innerHTML = `
      <div class="ob-icon" style="width:64px;height:64px;border-radius:20px">${obIcon('chip')}</div>
      <div class="ob-title">${esc(t('obS1T'))}</div>
      <div class="ob-sub">${esc(t('obS1S'))}</div>`;
    next.dataset.action = '';
    next.textContent = t('obS1B');
  } else if(step === 's2'){
    const perms = [
      {k:'calendar', label: t('obPermCal'), sub: t('obPermCalS')},
      {k:'microphone', label: t('obPermMic'), sub: t('obPermMicS')},
      {k:'location', label: t('obPermLoc'), sub: t('obPermLocS')},
    ];
    body.innerHTML = `
      <div class="ob-icon">${obIcon('perm')}</div>
      <div class="ob-title">${esc(t('obS2T'))}</div>
      <div class="ob-sub">${esc(t('obS2S'))}</div>
      ${perms.map(p=>`
        <div class="ob-row">
          <div style="display:flex;align-items:center;gap:12px">
            ${obPermIcon(p.k, _ob.perms[p.k])}
            <div><div class="ob-row-txt">${esc(p.label)}</div><div class="ob-row-sub">${esc(p.sub)}</div></div>
          </div>
          ${_ob.perms[p.k]
            ? `<span style="font-size:12px;font-weight:700;color:var(--success)">${esc(t('obGranted'))}</span>`
            : (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.PiSynapse
              ? `<button class="ob-btn ghost" style="font-size:12px;padding:7px 12px" onclick="obGrantPerm('${p.k}')">${esc(t('obGrant'))}</button>`
              : `<span style="font-size:12px;color:var(--text3)">web</span>`)}
        </div>`).join('')}
      <div class="ob-hint">${esc(t('obSkipPerm'))}</div>`;
    next.dataset.action = '';
    next.textContent = t('obS1B');
  } else if(step === 's3'){
    const curCity = window.config?.default_city || '';
    body.innerHTML = `
      <div class="ob-icon">${obIcon('user')}</div>
      <div class="ob-title">${esc(t('obS3T'))}</div>
      <div class="ob-sub">${esc(t('obS3S'))}</div>
      <div class="ob-field"><label for="ob-aname">${esc(t('obAsync'))}</label><input class="ob-input" id="ob-aname" maxlength="40" placeholder="${esc(t('obAsyncPh'))}" value="${esc(window.config?.assistant_user||'')}"></div>
      <div class="ob-field"><label for="ob-city">${esc(t('obCity'))} <em style="font-style:normal;font-size:11px;color:var(--text3)">(${esc(t('optional'))})</em></label><input class="ob-input" id="ob-city" maxlength="40" placeholder="${esc(t('obCityPh'))}" value="${esc(curCity)}"></div>
      ${_NATIVE && _ob.perms.location && !curCity ? `<div class="ob-hint" id="ob-city-detect">${esc(t('obCityDetecting'))}</div>` : ''}`;
    if(_NATIVE && _ob.perms.location && !curCity){
      setTimeout(()=>autoDetectCity(), 150);
    }
    next.dataset.action = 'save';
    next.textContent = t('obS1B');
  } else if(step === 's6'){
    if(_NATIVE){
      body.innerHTML = `
        <div class="ob-icon">${obIcon('server')}</div>
        <div class="ob-title">${esc(t('obS6T'))}</div>
        <div class="ob-sub">${esc(t('obS6S'))}</div>
        <div class="ob-field"><label for="ob-surl">${esc(t('obS6Url'))}</label><input class="ob-input" id="ob-surl" maxlength="200" placeholder="${esc(t('obS6UrlPh'))}" value="${esc(window.config?.server_url || '')}"></div>
        <div class="ob-field"><label for="ob-suser">${esc(t('obS6User'))}</label><input class="ob-input" id="ob-suser" maxlength="200" autocomplete="off" placeholder="${esc(t('obS6UserPh'))}" value="${esc(window.config?.server_user || '')}"></div>
        <div class="ob-field"><label for="ob-skey">${esc(t('obS6Key'))}</label><input class="ob-input" id="ob-skey" type="password" maxlength="200" autocomplete="off" placeholder="${esc(t('obS6KeyPh'))}" value="${esc((window._settingsData&&window._settingsData.SERVER_API_KEY)?(window._settingsData.SERVER_API_KEY.value||''):'')}"></div>
        <div class="ob-hint">${esc(t('obS6Hint'))}</div>`;
    } else {
      const savedUrl = localStorage.getItem('ps_server_url') || (window.location.origin.startsWith('http') ? window.location.origin : '');
      const savedKey = localStorage.getItem('ps_api_key') || '';
      body.innerHTML = `
        <div class="ob-icon">${obIcon('server')}</div>
        <div class="ob-title">${esc(t('obS6T'))}</div>
        <div class="ob-sub">${esc(t('obS6S'))}</div>
        <div class="ob-field"><label for="ob-surl">${esc(t('obS6Url'))}</label><input class="ob-input" id="ob-surl" maxlength="200" placeholder="${esc(t('obS6UrlPh'))}" value="${esc(savedUrl)}"></div>
        <div class="ob-field"><label for="ob-skey">${esc(t('obS6Key'))}</label><input class="ob-input" id="ob-skey" type="password" maxlength="200" autocomplete="off" placeholder="${esc(t('obS6KeyPh'))}" value="${esc(savedKey)}"></div>
        <div class="ob-hint">${esc(t('obS6Hint'))}</div>`;
    }
    next.dataset.action = 'server';
    next.textContent = t('obS1B');
  } else if(step === 's4'){
    body.innerHTML = `
      <div class="ob-icon">${obIcon('chip')}</div>
      <div class="ob-title">${esc(t('obS4T'))}</div>
      <div class="ob-sub">${esc(t('obS4S'))}</div>
      <div id="ob-model-status"><div class="ob-status"><span class="spinner"></span><span class="ob-status-msg">${esc(t('obModelLoading'))}</span></div></div>`;
    next.dataset.action = '';
    next.textContent = t('obS1B');
  } else if(step === 's5'){
    body.innerHTML = `
      <div class="ob-icon">${obIcon('tour')}</div>
      <div class="ob-title">${esc(t('obS5T'))}</div>
      <div class="ob-sub">${esc(t('obS5S'))}</div>
      ${[t('obTip1'),t('obTip2'),t('obTip3'),t('obTip4')].map(tp=>`
        <div class="ob-row"><div style="display:flex;align-items:center;gap:12px"><span style="color:var(--accent);font-weight:700">•</span><div class="ob-row-txt">${esc(tp)}</div></div></div>`).join('')}`;
    next.dataset.action = '';
    next.textContent = t('obDone');
  }
}

async function autoDetectCity(){
  if(!_NATIVE) return;
  const field = document.getElementById('ob-city');
  if(!field) return;
  try{
    const st = await _NATIVE.permissionStatus();
    if(!(st && st.location)) return;
    const r = await _NATIVE.detectCity();
    if(r && r.ok && r.city){
      if(!field.value.trim()) field.value = r.city;
      const hint = document.getElementById('ob-city-detect');
      if(hint) hint.textContent = r.city;
      // Persist immediately so weather works even if the user skips the step.
      try{ await api('PATCH','/config/settings',{values:{DEFAULT_CITY:r.city}}); }catch(e){}
      window.config = await api('GET','/config');
    }
  }catch(e){}
}

async function obGrantPerm(kind){
  try{
    if(_NATIVE){
      await _NATIVE.requestPermission({kind});
      // give the OS time to settle before reading back the result
      await new Promise(r=>setTimeout(r,1200));
      const st = await _NATIVE.permissionStatus();
      if(st) _ob.perms[kind]=!!st[kind];
    }
  } catch(e){}
  renderOnboarding();
}

async function startOnboarding(){
  if(localStorage.getItem('ps_onboarded')) return;
  // initialize permission status if native
  if(_NATIVE){
    try{
      const st = await _NATIVE.permissionStatus();
      if(st) Object.assign(_ob.perms, { calendar:!!st.calendar, microphone:!!st.microphone, location:!!st.location });
    }catch(e){}
  }
  document.getElementById('onboard').classList.add('open');
  _ob.step = 0;
  renderOnboarding();
  if(OB_STEPS[_ob.step] === 's4') preloadModelCheck();
}

function finishOnboarding(){
  localStorage.setItem('ps_onboarded','1');
  document.getElementById('onboard').classList.remove('open');
  document.body.classList.remove('settings-open');
}

// ── Ticker (Marquee) ────────────────────────────────────────────────────────
async function startTicker(){
  await refreshTicker();
  setInterval(refreshTicker, 3_600_000);
  setInterval(rotateTicker,  8_000);
  startStalenessScan();
}

// ── Server health (status dot) ──────────────────────────────────────────────────
async function pollHealth(){
  if(loading) return; // don't fight the "thinking" pulse mid-request
  const dot = document.getElementById('status-dot');
  if(!dot) return;
  try{
    const h = await api('GET','/health');
    const deps = h.dependencies || {};
    const bad = Object.entries(deps).filter(([,v]) => v === 'error');
    const warn = Object.entries(deps).filter(([,v]) => v === 'warn');
    dot.classList.remove('ok','warn','error');
    if(bad.length || warn.length){
      const notes = bad.concat(warn).map(([k,v]) => k+': '+v);
      dot.classList.add(bad.length ? 'error' : 'warn');
      dot.title = notes.join('\n');
    } else {
      dot.classList.add('ok');
      dot.title = 'piSynapse: all systems operational';
    }
  }catch(e){
    dot.classList.remove('ok','warn','error');
    dot.classList.add('error');
    dot.title = 'piSynapse: server unreachable';
  }
}

async function startHealthPoll(){
  await pollHealth();
  setInterval(pollHealth, 60_000);
}

async function refreshTicker(){
  const sunCloudSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"></path><path d="M22 16.92v-.08a5 5 0 0 0-4.32-4.94A5.89 5.89 0 0 0 12 7.5a5.5 5.5 0 0 0-4.72 2.68A5.5 5.5 0 0 0 3 15.5a4.5 4.5 0 0 0 4.5 4.5h10a4.5 4.5 0 0 0 4.5-4.58z"></path></svg>`;
  const calendarSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>`;
  if(!window._tickerIcons) window._tickerIcons = { sun: sunCloudSvg, cal: calendarSvg };
  if(!window._weatherIcons) window._weatherIcons = {
    clear:   `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"></path></svg>`,
    partly:  `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M12 2v2"></path><path d="m5.4 5.4 1.41 1.41"></path><path d="M20 12h2"></path><path d="m17.24 6.81-1.41 1.41"></path><path d="M15.9 12.66a4 4 0 1 0-5.93-3.85"></path><path d="M13 21H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"></path></svg>`,
    cloud:   `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"></path></svg>`,
    fog:     `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M4 14.9A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.24"></path><path d="M16 17H7"></path><path d="M17 21H9"></path></svg>`,
    drizzle: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M4 14.9A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.24"></path><path d="M8 19v1"></path><path d="M8 14v1"></path><path d="M16 19v1"></path><path d="M16 14v1"></path><path d="M12 21v1"></path><path d="M12 16v1"></path></svg>`,
    rain:    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M4 14.9A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.24"></path><path d="M16 14v6"></path><path d="M8 14v6"></path><path d="M12 16v6"></path></svg>`,
    snow:    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M4 14.9A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.24"></path><path d="M8 15h.01"></path><path d="M8 19h.01"></path><path d="M12 17h.01"></path><path d="M12 21h.01"></path><path d="M16 15h.01"></path><path d="M16 19h.01"></path></svg>`,
    storm:   `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M6 16.3A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 .5 8.97"></path><path d="m13 12-3 5h4l-3 5"></path></svg>`,
    unknown: sunCloudSvg,
  };
  try{ const w=await api('GET','/widget/weather'); _cachedWeatherRaw=w.summary||null; _cachedWeatherSummary=_cachedWeatherRaw; _cachedWeatherKind=w.kind||null; _cachedWeatherTemp=w.temp_c; _cachedWeatherCond=w.condition||null; _cachedWeatherWmo=w.wmo_code; } catch{_cachedWeatherRaw=null; _cachedWeatherSummary=null; _cachedWeatherKind=null; _cachedWeatherTemp=null; _cachedWeatherCond=null; _cachedWeatherWmo=null; }
  try{ const c=await api('GET','/widget/calendar'); _cachedEvents=c.events||[]; } catch{ _cachedEvents=null; }
  rebuildTickerFromCache();
}

function rebuildTickerFromCache(){
  const icons = window._tickerIcons || {};
  const infoSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
  tickerItems = [];
  if(_cachedWeatherRaw){
    let text;
    if(_cachedWeatherWmo != null){
      text = _cachedWeatherTemp != null ? `${_cachedWeatherTemp}°C · ${wmoLabel(_cachedWeatherWmo)}` : wmoLabel(_cachedWeatherWmo);
    } else if(_cachedWeatherCond){
      text = _cachedWeatherTemp != null ? `${_cachedWeatherTemp}°C · ${_cachedWeatherCond}` : _cachedWeatherCond;
    } else {
      text = _cachedWeatherRaw.replace(/feels like/gi, t('feelsLike'));
    }
    const wicons = window._weatherIcons || {};
    tickerItems.push({ icon: wicons[wmoIconKind(_cachedWeatherWmo)] || wicons[_cachedWeatherKind] || icons.sun || infoSvg, text });
  }
  if(_cachedEvents !== null){
    const evs = freshEvents(_cachedEvents);
    if(evs.length){
      evs.forEach(ev => tickerItems.push({ icon: icons.cal||infoSvg, text:`${ev.time} \u2014 ${ev.title}` }));
    } else {
      tickerItems.push({ icon: icons.cal||infoSvg, text: t('noEvents') });
    }
  }
  if(!tickerItems.length) tickerItems.push({ icon: infoSvg, text:'piSynapse \u2014 Memory Active' });
  tickerIdx = 0;
  const _tickers = [document.getElementById('ticker'), document.getElementById('top-ticker')];
  clearTimeout(_tickerFadeTO);
  _tickers.forEach(el => { if(el) el.style.opacity = '0'; });
  showTickerItem(0);
  requestAnimationFrame(()=>{ _tickers.forEach(el => { if(el) el.style.opacity = '1'; }); });
}

// ── Staleness scan (calendar widget) ────────────────────────────────────────────
// Client-side only: drops events whose start time has already passed, using the
// cached /widget/calendar data. No extra network requests.
function freshEvents(events){
  // Bu fonksiyon yalnızca /widget/calendar'ın SADECE bugünün etkinliklerini
  // döndürdüğü varsayımına dayanır — çok günlük etkinlik desteği eklenirse
  // burada tarih karşılaştırması da gerekir.
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  return (events || []).filter(ev => {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(ev.time || ''));
    if(!m) return true; // unparseable time: keep it rather than risk hiding a real event
    return (parseInt(m[1], 10) * 60 + parseInt(m[2], 10)) >= nowMin;
  });
}

function scanStaleness(){
  if(!_cachedEvents || !_cachedEvents.length) return;
  const fresh = freshEvents(_cachedEvents);
  if(fresh.length === _cachedEvents.length) return; // nothing to prune
  _cachedEvents = fresh;
  rebuildTickerFromCache();
}

function startStalenessScan(){
  scanStaleness();
  setInterval(scanStaleness, 60_000);
}

function showTickerItem(idx){
  const item = tickerItems[idx] || tickerItems[0]; if(!item) return;
  const singleContent = `<div style="display:inline-flex;align-items:center;gap:8px;padding-left:8px;padding-right:30px;font-size:12.5px;color:var(--text2);">${item.icon} <span style="font-weight:500;">${esc(item.text)}</span></div>`;
  const botInner = document.getElementById('ticker-text-inner'); if(botInner) applySeamlessMarquee(botInner, singleContent);
  const topInner = document.getElementById('top-ticker-text-inner'); if(topInner) applySeamlessMarquee(topInner, singleContent);
}

function applySeamlessMarquee(element, singleHtml) {
  element.innerHTML = `<div class="marquee-content">${singleHtml}</div>`;
  const contentNode = element.querySelector('.marquee-content'); contentNode.style.animation = 'none';
  setTimeout(() => {
     const containerWidth = element.parentElement.offsetWidth, contentWidth = contentNode.firstElementChild.offsetWidth;
     if (contentWidth > containerWidth && containerWidth > 0) {
         contentNode.innerHTML = singleHtml + singleHtml;
         const duration = Math.max(10, contentWidth / 25); contentNode.style.animation = `marquee ${duration}s linear infinite`;
     } else { contentNode.innerHTML = singleHtml; }
  }, 30);
}

let _tickerFadeTO = null;
function rotateTicker(){
  if(tickerItems.length <= 1) return;
  tickerIdx = (tickerIdx + 1) % tickerItems.length;
  const tickers = [document.getElementById('ticker'), document.getElementById('top-ticker')];
  clearTimeout(_tickerFadeTO);
  tickers.forEach(el => { if(el) el.style.opacity = '0'; });
  _tickerFadeTO = setTimeout(()=>{ showTickerItem(tickerIdx); tickers.forEach(el => { if(el) el.style.opacity = '1'; }); }, 400);
}

// ── Search / Compact ────────────────────────────────────────────
let _searchQuery = '';

function filterSessions(q){
  _searchQuery = q.toLowerCase().trim();
  if(!_searchQuery){ clearTimeout(_searchTimer); renderSessions(sessionList, false); return; }
  _debounceSearch(q);
}

let _searchTimer=null;
function _debounceSearch(q){
  clearTimeout(_searchTimer);
  _searchTimer=setTimeout(async()=>{
    const qq=q.toLowerCase().trim();
    // Offline fast-path: no network, local title filter instantly
    if(!navigator.onLine){
      const local=sessionList.filter(s=>sessName(s).toLowerCase().includes(qq));
      renderSessions(local, false);
      return;
    }
    const ctrl=new AbortController();
    const to=setTimeout(()=>ctrl.abort(), 800);
    try{
      const h={}; const k=getApiKey(); if(k) h['X-API-Key']=k;
      const r=await fetch(API+'/chat/search?q='+encodeURIComponent(q),{headers:h, signal: ctrl.signal});
      clearTimeout(to);
      if(!r.ok) throw new Error('search failed');
      const d=await r.json();
      if(!d.results||!d.results.length){
        const local=sessionList.filter(s=>sessName(s).toLowerCase().includes(qq));
        renderSessions(local, false);
        return;
      }
      const snippetMap=new Map(d.results.map(r=>[r.session_id, r.snippet||""]));
      const ids=new Set(snippetMap.keys());
      const final=sessionList.filter(s=>ids.has(s.session_id))
        .map(s=>({...s, _snippet: snippetMap.get(s.session_id)||""}));
      renderSessions(final, false);
    }catch{
      clearTimeout(to);
      const local=sessionList.filter(s=>sessName(s).toLowerCase().includes(qq));
      renderSessions(local, false);
    }
  },150);
}
window.addEventListener('online', ()=>{
  if(_searchQuery) _debounceSearch(_searchQuery);
});
window.addEventListener('offline', ()=>{
  if(_searchQuery){
    const local=sessionList.filter(s=>sessName(s).toLowerCase().includes(_searchQuery));
    renderSessions(local, false);
  }
});

function toggleSearch(){
  const box = document.getElementById('sb-search'), toggle = document.getElementById('search-toggle');
  if(!box) return;
  const open = box.classList.toggle('open');
  if(toggle) toggle.classList.toggle('on', open);
  const inp = document.getElementById('sess-search');
  if(open){ if(inp) inp.focus(); }
  else {
    if(inp){ inp.value=''; inp.blur(); }
    clearTimeout(_searchTimer);
    _searchQuery='';
    requestAnimationFrame(()=> renderSessions(sessionList, false));
  }
}

function toggleCompact(){
  document.body.classList.toggle('sidebar-compact');
  localStorage.setItem('ps_compact', document.body.classList.contains('sidebar-compact') ? '1' : '');
}

function applyStagger(){
  document.querySelectorAll('.sess-item').forEach((el, i) => {
    el.style.animationDelay = (0.02 * (i + 1)) + 's';
    // Release the entrance fill once it finishes (animation pins transform,
    // which would otherwise swallow the :active press scale forever).
    const done = (e) => {
      if(e.animationName !== 'msgSlideIn') return;
      el.style.animation = 'none';
      el.style.animationDelay = '';
      // Base rule has no opacity, so killing the fill must not drop the item
      // back to opacity:0 — force it visible again (invisible-but-clickable bug).
      el.style.opacity = '1';
      el.removeEventListener('animationend', done);
    };
    el.addEventListener('animationend', done, { once: true });
  });
}

// ── Sidebar Controls ────────────────────────────────────────────────────────────
let _sidebarToggleTimer = null;
function toggleSidebar(){
  if(window.innerWidth <= 768) {
    if(document.body.classList.contains('sidebar-mobile-open')){
      closeSidebar(); return;
    }
    const btn = document.getElementById('logo-btn');
    btn.classList.add('btn-press');
    if(navigator.vibrate) navigator.vibrate(12);
    _sidebarToggleTimer = setTimeout(() => {
      btn.classList.remove('btn-press');
      document.body.classList.add('sidebar-mobile-open');
      document.getElementById('overlay').classList.add('show');
    }, 90);
  } else {
    document.body.classList.toggle('sidebar-closed'); if(document.body.classList.contains('sidebar-closed') && memOpen) toggleMem();
  }
}
function closeSidebar(){
  document.body.classList.remove('sidebar-mobile-open'); document.getElementById('overlay').classList.remove('show'); if(memOpen) toggleMem();
}

// ── Utility Functions ───────────────────────────────────────────────────────────
function scrollEnd(force = false){ const e = document.getElementById('messages'); if (force || (e.scrollHeight - e.scrollTop - e.clientHeight < 150)) { e.scrollTop = e.scrollHeight; } }
function timeNow(){ return new Date().toLocaleTimeString(lang==='tr' ? 'tr-TR' : 'en-GB', {hour:'2-digit', minute:'2-digit'}); }
function relTime(ts){
  if(!ts) return '';
  // SQLite CURRENT_TIMESTAMP is UTC and may use a space separator — normalize to ISO-8601
  const iso = ts.endsWith('Z') ? ts : ts.replace(' ','T')+'Z';
  const d=Date.now()-new Date(iso).getTime();
  if(lang==='en'){ if(d<60000) return 'just now'; if(d<3600000) return Math.floor(d/60000)+'m'; if(d<86400000) return Math.floor(d/3600000)+'h'; return Math.floor(d/86400000)+'d'; }
  if(d<60000) return 'az \u00F6nce'; if(d<3600000) return Math.floor(d/60000)+'dk'; if(d<86400000) return Math.floor(d/3600000)+'sa'; return Math.floor(d/86400000)+'g';
}
let toastTimer; function toast(msg, err=false){ const el=document.getElementById('toast'); el.textContent=msg; el.classList.toggle('err',err); el.classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.classList.remove('show'), 3000); }

// ── Sidebar Swipe Gesture (mobile) ────────────────────────────────
let _swipeStartX = 0, _swipeStartY = 0, _swipeOnThink = false, _swipeInScrollable = false;
function _resetSwipe(){ _swipeStartX = 0; _swipeStartY = 0; _swipeOnThink = false; _swipeInScrollable = false; }
document.addEventListener('touchstart', e => {
  const touch = e.touches[0];
  _swipeStartX = touch.clientX;
  _swipeStartY = touch.clientY;
  _swipeOnThink = !!(e.target && e.target.closest && e.target.closest('#think-popover'));
  _swipeInScrollable = !!(e.target && e.target.closest && e.target.closest('.code-wrapper,pre,table,.chip-track,.w-chip,textarea,#msg-input,.sess-list'));
}, {passive: true});
document.addEventListener('touchend', _resetSwipe, {passive: true});
document.addEventListener('touchcancel', _resetSwipe, {passive: true});

document.addEventListener('touchmove', e => {
  if(window.innerWidth > 768 || _swipeOnThink || _swipeInScrollable) return;
  const touch = e.touches[0];
  const dx = touch.clientX - _swipeStartX;
  const dy = touch.clientY - _swipeStartY;
  if(Math.abs(dx) < 15 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
  if(dx > 30 && !document.body.classList.contains('sidebar-mobile-open') && _swipeStartX < 150){
    document.body.classList.add('sidebar-mobile-open');
    document.getElementById('overlay').classList.add('show');
  } else if(dx < -30 && document.body.classList.contains('sidebar-mobile-open')){
    closeSidebar();
  }
}, {passive: true});

// ── Hold-to-Record ────────────────────────────────────────────────
let _holdTimer = null;

function setupHoldToRecord(){
  const btn = document.getElementById('mic-btn');
  if(!btn) return;

  const start = (e) => {
    if(voiceState !== 'idle') return;
    e.preventDefault();
    _holdTimer = setTimeout(() => {
      _holdTimer = null;
      startVoice();
    }, 200);
  };

  const end = (e) => {
    if(_holdTimer){ clearTimeout(_holdTimer); _holdTimer = null; return; }
    if(voiceState === 'recording'){
      e.preventDefault();
      stopVoice();
    }
  };

  btn.addEventListener('mousedown', start);
  btn.addEventListener('mouseup', end);
  btn.addEventListener('mouseleave', () => { if(_holdTimer){ clearTimeout(_holdTimer); _holdTimer = null; } });
  btn.addEventListener('touchstart', start, {passive: true});
  btn.addEventListener('touchend', end);
}

// ── Setup on load ───────────────────────────────────────────────
// Restore compact mode
if(localStorage.getItem('ps_compact')) document.body.classList.add('sidebar-compact');

// ── PWA Service Worker ──────────────────────────────────────
// Browser-only: the native WebView loads assets from the package and its
// scheme/local server makes SW caching unreliable — never register there.
if(!_NATIVE && 'serviceWorker' in navigator){
  navigator.serviceWorker.register('/sw.js').catch(()=>{});
}
// Native: purge any service worker registration that survived from older
// builds (a stale controller would serve outdated cached assets on device).
if(_NATIVE && 'serviceWorker' in navigator){
  navigator.serviceWorker.getRegistrations().then(rs=>{ rs.forEach(r=>r.unregister()); }).catch(()=>{});
}

// ── Standalone PWA adjustments ──────────────────────────────────────────────
if(window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone){
  document.body.classList.add('pwa-standalone');
}
