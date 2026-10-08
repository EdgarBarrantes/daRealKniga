"""Builds the translated project pages (docs/ru, docs/bg, docs/fr) from the English docs/index.html.

Each English text block is replaced with its translation; the script stops if a block isn't found,
so an edit to the English page can't silently leave English text on the translated pages. After
editing either, run this, then `python tests/accuracy.py --save` (or report.update_site) to fill in
the translated benchmark section.

    python packaging/make_site.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
LANGS = {"en": "English", "ru": "Русский", "bg": "Български", "fr": "Français"}
GH = "https://github.com/EdgarBarrantes/daRealKniga"

# English block -> translation, per language (the order follows the page)
T = {}

T["ru"] = {
    '<title>daRealKniga</title>': '<title>daRealKniga — OCR для славянских языков</title>',
    'content="Free OCR for old books, archives and documents in Slavic languages and English: turns scans and phone photos into faithful, searchable PDFs, even when Cyrillic and Latin are mixed."':
        'content="Бесплатное распознавание текста для старых книг, архивов и документов на славянских языках и английском: из сканов и фото с телефона — точные копии в PDF с поиском, даже когда кириллица и латиница перемешаны."',
    'content="daRealKniga: OCR for Slavic and English documents"': 'content="daRealKniga: OCR для славянских и английских текстов"',
    'content="Scans and phone photos in, clean searchable PDFs out. Reads mixed Cyrillic and Latin text far better than plain OCR."':
        'content="Сканы и фото с телефона на входе, чистые PDF с поиском на выходе. Смешанный кириллический и латинский текст читается гораздо лучше, чем обычным OCR."',
    '<p class="tag">Turn old books, archives and everyday documents into faithful, <strong>searchable</strong> digital copies. Made for Slavic languages and English, even mixed on one page.</p>':
        '<p class="tag">Превращает старые книги, архивы и повседневные документы в точные цифровые копии, <strong>по которым можно искать</strong>. Создано для славянских языков и английского, даже вперемешку на одной странице.</p>',
    '<p class="gloss"><em>да</em> = yes, <em>книга</em> = book: “yes, a real book”, with real, searchable text.</p>':
        '<p class="gloss">«Да, настоящая книга»: с настоящим текстом, по которому можно искать.</p>',
    '>Get it, free</a>': '>Скачать бесплатно</a>',
    '>How good is it?</a>': '>Насколько это хорошо?</a>',
    '>Source on GitHub</a>': '>Исходный код на GitHub</a>',
    'alt="A curled phone photo of a Bulgarian and English page is dropped into daRealKniga; a clean, searchable PDF comes out; plain OCR\'s misread words are shown next to daRealKniga\'s."':
        'alt="Изогнутое фото страницы на болгарском и английском перетаскивают в daRealKniga; получается чистый PDF с поиском; ошибки обычного OCR показаны рядом с результатом daRealKniga."',
    '<p class="caption">A real run: a phone photo in, a searchable PDF out, and plain OCR on the same photo for comparison.</p>':
        '<p class="caption">Настоящий запуск: на входе фото с телефона, на выходе PDF с поиском, а для сравнения — обычный OCR на том же фото (интерфейс на английском; программа доступна и на русском).</p>',
    '<h2 id="what">What it does</h2>': '<h2 id="what">Что она делает</h2>',
    '<h3>Searchable PDFs</h3><p>Turns DjVu books, image PDFs, photos and scans into PDFs you can search, select and copy. It also writes a plain text file and, for DjVu books, a searchable DjVu.</p>':
        '<h3>PDF с поиском</h3><p>Превращает книги в DjVu, PDF из картинок, фото и сканы в PDF, где текст можно искать, выделять и копировать. Также сохраняет простой текстовый файл, а для книг в DjVu — DjVu с поиском.</p>',
    '<h3>Cyrillic and Latin, mixed</h3><p>Textbooks, dictionaries and bilingual documents keep each word in its own alphabet. Look-alike letters (<code>а</code>/<code>a</code>, <code>р</code>/<code>p</code>, <code>Н</code>/<code>H</code>) no longer break search.</p>':
        '<h3>Кириллица и латиница вперемешку</h3><p>В учебниках, словарях и двуязычных документах каждое слово остаётся в своём алфавите. Похожие буквы (<code>а</code>/<code>a</code>, <code>р</code>/<code>p</code>, <code>Н</code>/<code>H</code>) больше не ломают поиск.</p>',
    '<h3>Photos, not just scans</h3><p>Curled, tilted, shadowed pages from a phone are flattened and cleaned up first, and every page ends up the same size.</p>':
        '<h3>Не только сканы, но и фото</h3><p>Изогнутые, наклонённые, затенённые страницы с телефона сначала выпрямляются и очищаются, а все страницы получаются одного размера.</p>',
    '<h3>Your language, your computer</h3><p>The window comes in 31 languages, all Slavic ones included. Everything runs on your computer: your documents never leave it.</p>':
        '<h3>Ваш язык, ваш компьютер</h3><p>Интерфейс доступен на 31 языке, включая все славянские. Всё работает на вашем компьютере: документы никуда не отправляются.</p>',
    '<h2 id="books">For old books and archives</h2>': '<h2 id="books">Для старых книг и архивов</h2>',
    '<p>daRealKniga is built for digitising whole books and collections, the way a library or an archive would want them: faithful to the original, consistent, and searchable.</p>':
        '<p>daRealKniga создана для оцифровки целых книг и собраний так, как этого ждут библиотеки и архивы: верно оригиналу, единообразно и с поиском.</p>',
    '<h3>The original stays intact</h3><p>DjVu scans keep their page images exactly as they are, with an invisible text layer added. A PDF and a plain-text file are written next to them.</p>':
        '<h3>Оригинал остаётся нетронутым</h3><p>В сканах DjVu изображения страниц сохраняются в точности, добавляется только невидимый текстовый слой. Рядом сохраняются PDF и текстовый файл.</p>',
    '<h3>Whole books, not just pages</h3><p>Hundreds of pages are processed in parallel. An interrupted run resumes where it stopped, and a page range lets you try the settings on a few pages first.</p>':
        '<h3>Целые книги, а не отдельные страницы</h3><p>Сотни страниц обрабатываются параллельно. Прерванная обработка продолжается с того же места, а диапазон страниц позволяет сначала проверить настройки на нескольких страницах.</p>',
    '<h3>Old print, uneven scans</h3><p>Every page ends up the same size, even when the scans don\'t match. Tested on Bulgarian and Russian editions from the 1970s, against their existing text.</p>':
        '<h3>Старая печать, разнородные сканы</h3><p>Все страницы получаются одного размера, даже если сканы различаются. Проверено на болгарских и русских изданиях 1970-х годов по их существующему тексту.</p>',
    '<h3>Catalogue-ready, and private</h3><p>Title and author are stored in the PDF. Everything runs on your own computer: collections never leave it, and the formats are open (PDF, DjVu, plain text).</p>':
        '<h3>Готово для каталога и конфиденциально</h3><p>Название и автор сохраняются в PDF. Всё работает на вашем компьютере: собрания никуда не уходят, а форматы открытые (PDF, DjVu, простой текст).</p>',
    '<h2 id="accuracy">Better than plain OCR</h2>': '<h2 id="accuracy">Лучше обычного OCR</h2>',
    '<p>Every sample is read three ways from the same page images: by Tesseract alone, by PaddleOCR alone, and by daRealKniga, which cleans the pages up, combines both engines word by word and corrects what they get wrong.</p>':
        '<p>Каждый образец читается тремя способами по одним и тем же изображениям страниц: только Tesseract, только PaddleOCR и daRealKniga, которая очищает страницы, объединяет оба движка слово за словом и исправляет их ошибки.</p>',
    '<p class="note">The samples, the scoring and how to rerun it yourself are described in the <a href="https://github.com/EdgarBarrantes/daRealKniga#tests">README</a>.</p>':
        '<p class="note">Образцы, способ оценки и как повторить проверку самостоятельно описаны в <a href="https://github.com/EdgarBarrantes/daRealKniga#tests">README</a> (на английском).</p>',
    '<h2 id="get-it">Get it</h2>': '<h2 id="get-it">Скачать</h2>',
    '<p>Free and open source (MIT). The first run downloads the OCR models: about 45&nbsp;MB, plus 10–15&nbsp;MB per language.</p>':
        '<p>Бесплатно и с открытым кодом (MIT). При первом запуске загружаются модели OCR: около 45&nbsp;МБ и ещё 10–15&nbsp;МБ на каждый язык.</p>',
    '<p>A single file with everything included. Make it executable and double-click it. Works on 64-bit distributions from about 2022 on.</p>':
        '<p>Один файл, в котором есть всё. Сделайте его исполняемым и запустите двойным щелчком. Работает в 64-битных дистрибутивах примерно с 2022 года.</p>',
    '>Download the AppImage</a>': '>Скачать AppImage</a>',
    '<span class="wip">work in progress</span>': '<span class="wip">в разработке</span>',
    '<p>Apple Silicon and Intel. Installed with Homebrew and a few Terminal commands.</p>':
        '<p>Apple Silicon и Intel. Устанавливается через Homebrew и несколько команд в Терминале.</p>',
    '>Install on macOS</a>': '>Установка на macOS</a>',
    '<p>64-bit Windows 10 and 11. Installed with a few PowerShell commands.</p>':
        '<p>64-битные Windows 10 и 11. Устанавливается несколькими командами PowerShell.</p>',
    '>Install on Windows</a>': '>Установка на Windows</a>',
    '<p class="note">macOS and Windows support is new: if something doesn\'t work, or the instructions are unclear, please <a href="https://github.com/EdgarBarrantes/daRealKniga/issues/new/choose">tell us</a>. Feedback is much appreciated.</p>':
        '<p class="note">Поддержка macOS и Windows появилась недавно: если что-то не работает или инструкции непонятны, пожалуйста, <a href="https://github.com/EdgarBarrantes/daRealKniga/issues/new/choose">напишите нам</a>. Мы будем очень благодарны за отзывы.</p>',
    '<h2 id="use">Using it</h2>': '<h2 id="use">Как пользоваться</h2>',
    '<p>Open the window, drop in a document, pick the text language and press <strong>Make searchable</strong>. Or use the command line (<code>drk</code> is short for <code>darealkniga</code>):</p>':
        '<p>Откройте окно, перетащите документ, выберите язык текста и нажмите <strong>Распознать текст</strong>. Или используйте командную строку (<code>drk</code> — короткая форма <code>darealkniga</code>):</p>',
    '<td>A Bulgarian textbook with English in it</td>': '<td>Болгарский учебник с английским текстом</td>',
    '<td>A Bulgarian book, with its title and author stored in the PDF</td>': '<td>Болгарская книга; название и автор сохраняются в PDF</td>',
    '<td>A single photo: a receipt, a letter, a note</td>': '<td>Одно фото: чек, письмо, записка</td>',
    '<td>A folder of page photos, in page order</td>': '<td>Папка с фотографиями страниц, по порядку</td>',
    '>Report a problem or suggest an idea</a> · MIT license': '>Сообщить о проблеме или предложить идею</a> · лицензия MIT',
    '<p>Built on Tesseract, PaddleOCR, UVDoc and DjVuLibre.</p>': '<p>Основано на Tesseract, PaddleOCR, UVDoc и DjVuLibre.</p>',
}

T["bg"] = {
    '<title>daRealKniga</title>': '<title>daRealKniga — OCR за славянски езици</title>',
    'content="Free OCR for old books, archives and documents in Slavic languages and English: turns scans and phone photos into faithful, searchable PDFs, even when Cyrillic and Latin are mixed."':
        'content="Безплатно разпознаване на текст за стари книги, архиви и документи на славянски езици и английски: от сканирания и снимки с телефон — точни копия в PDF с търсене, дори когато кирилица и латиница са смесени."',
    'content="daRealKniga: OCR for Slavic and English documents"': 'content="daRealKniga: OCR за славянски и английски текстове"',
    'content="Scans and phone photos in, clean searchable PDFs out. Reads mixed Cyrillic and Latin text far better than plain OCR."':
        'content="Сканирания и снимки с телефон на входа, чисти PDF файлове с търсене на изхода. Чете смесен кирилски и латински текст много по-добре от обикновения OCR."',
    '<p class="tag">Turn old books, archives and everyday documents into faithful, <strong>searchable</strong> digital copies. Made for Slavic languages and English, even mixed on one page.</p>':
        '<p class="tag">Превръща стари книги, архиви и всекидневни документи в точни дигитални копия, <strong>в които може да се търси</strong>. Създадена за славянските езици и английския, дори смесени на една страница.</p>',
    '<p class="gloss"><em>да</em> = yes, <em>книга</em> = book: “yes, a real book”, with real, searchable text.</p>':
        '<p class="gloss">„Да, истинска книга“: с истински текст, в който може да се търси.</p>',
    '>Get it, free</a>': '>Изтеглете безплатно</a>',
    '>How good is it?</a>': '>Колко е добра?</a>',
    '>Source on GitHub</a>': '>Изходен код в GitHub</a>',
    'alt="A curled phone photo of a Bulgarian and English page is dropped into daRealKniga; a clean, searchable PDF comes out; plain OCR\'s misread words are shown next to daRealKniga\'s."':
        'alt="Извита снимка на страница на български и английски се пуска в daRealKniga; излиза чист PDF с търсене; грешките на обикновения OCR са показани до резултата на daRealKniga."',
    '<p class="caption">A real run: a phone photo in, a searchable PDF out, and plain OCR on the same photo for comparison.</p>':
        '<p class="caption">Истинско изпълнение: снимка с телефон на входа, PDF с търсене на изхода и обикновен OCR на същата снимка за сравнение (интерфейсът е на английски; програмата е достъпна и на български).</p>',
    '<h2 id="what">What it does</h2>': '<h2 id="what">Какво прави</h2>',
    '<h3>Searchable PDFs</h3><p>Turns DjVu books, image PDFs, photos and scans into PDFs you can search, select and copy. It also writes a plain text file and, for DjVu books, a searchable DjVu.</p>':
        '<h3>PDF с търсене</h3><p>Превръща книги в DjVu, PDF файлове от изображения, снимки и сканирания в PDF, в който текстът може да се търси, маркира и копира. Записва и обикновен текстов файл, а за книгите в DjVu — DjVu с търсене.</p>',
    '<h3>Cyrillic and Latin, mixed</h3><p>Textbooks, dictionaries and bilingual documents keep each word in its own alphabet. Look-alike letters (<code>а</code>/<code>a</code>, <code>р</code>/<code>p</code>, <code>Н</code>/<code>H</code>) no longer break search.</p>':
        '<h3>Кирилица и латиница, смесени</h3><p>В учебници, речници и двуезични документи всяка дума остава в своята азбука. Еднаквите на вид букви (<code>а</code>/<code>a</code>, <code>р</code>/<code>p</code>, <code>Н</code>/<code>H</code>) вече не развалят търсенето.</p>',
    '<h3>Photos, not just scans</h3><p>Curled, tilted, shadowed pages from a phone are flattened and cleaned up first, and every page ends up the same size.</p>':
        '<h3>Не само сканирания, но и снимки</h3><p>Извитите, наклонени и засенчени страници от телефон първо се изправят и почистват, а всички страници стават с еднакъв размер.</p>',
    '<h3>Your language, your computer</h3><p>The window comes in 31 languages, all Slavic ones included. Everything runs on your computer: your documents never leave it.</p>':
        '<h3>Вашият език, вашият компютър</h3><p>Интерфейсът е на 31 езика, включително всички славянски. Всичко работи на вашия компютър: документите ви не го напускат.</p>',
    '<h2 id="books">For old books and archives</h2>': '<h2 id="books">За стари книги и архиви</h2>',
    '<p>daRealKniga is built for digitising whole books and collections, the way a library or an archive would want them: faithful to the original, consistent, and searchable.</p>':
        '<p>daRealKniga е създадена за дигитализиране на цели книги и колекции така, както биха ги искали библиотеките и архивите: вярно на оригинала, еднообразно и с търсене.</p>',
    '<h3>The original stays intact</h3><p>DjVu scans keep their page images exactly as they are, with an invisible text layer added. A PDF and a plain-text file are written next to them.</p>':
        '<h3>Оригиналът остава непокътнат</h3><p>Сканиранията в DjVu запазват изображенията на страниците точно такива, каквито са, като се добавя само невидим текстов слой. До тях се записват PDF и текстов файл.</p>',
    '<h3>Whole books, not just pages</h3><p>Hundreds of pages are processed in parallel. An interrupted run resumes where it stopped, and a page range lets you try the settings on a few pages first.</p>':
        '<h3>Цели книги, а не отделни страници</h3><p>Стотици страници се обработват паралелно. Прекъсната обработка продължава оттам, докъдето е стигнала, а с диапазон от страници можете първо да изпробвате настройките на няколко страници.</p>',
    '<h3>Old print, uneven scans</h3><p>Every page ends up the same size, even when the scans don\'t match. Tested on Bulgarian and Russian editions from the 1970s, against their existing text.</p>':
        '<h3>Стар печат, различни сканирания</h3><p>Всички страници стават с еднакъв размер, дори когато сканиранията се различават. Изпробвана върху български и руски издания от 70-те години спрямо съществуващия им текст.</p>',
    '<h3>Catalogue-ready, and private</h3><p>Title and author are stored in the PDF. Everything runs on your own computer: collections never leave it, and the formats are open (PDF, DjVu, plain text).</p>':
        '<h3>Готово за каталога и поверително</h3><p>Заглавието и авторът се записват в PDF файла. Всичко работи на вашия компютър: колекциите не го напускат, а форматите са отворени (PDF, DjVu, обикновен текст).</p>',
    '<h2 id="accuracy">Better than plain OCR</h2>': '<h2 id="accuracy">По-добра от обикновения OCR</h2>',
    '<p>Every sample is read three ways from the same page images: by Tesseract alone, by PaddleOCR alone, and by daRealKniga, which cleans the pages up, combines both engines word by word and corrects what they get wrong.</p>':
        '<p>Всеки образец се чете по три начина от едни и същи изображения на страниците: само с Tesseract, само с PaddleOCR и с daRealKniga, която почиства страниците, съчетава двете програми дума по дума и поправя грешките им.</p>',
    '<p class="note">The samples, the scoring and how to rerun it yourself are described in the <a href="https://github.com/EdgarBarrantes/daRealKniga#tests">README</a>.</p>':
        '<p class="note">Образците, начинът на оценяване и как да повторите проверката сами са описани в <a href="https://github.com/EdgarBarrantes/daRealKniga#tests">README</a> (на английски).</p>',
    '<h2 id="get-it">Get it</h2>': '<h2 id="get-it">Изтегляне</h2>',
    '<p>Free and open source (MIT). The first run downloads the OCR models: about 45&nbsp;MB, plus 10–15&nbsp;MB per language.</p>':
        '<p>Безплатна и с отворен код (MIT). При първото пускане се изтеглят моделите за OCR: около 45&nbsp;MB и още 10–15&nbsp;MB за всеки език.</p>',
    '<p>A single file with everything included. Make it executable and double-click it. Works on 64-bit distributions from about 2022 on.</p>':
        '<p>Един файл, в който има всичко. Направете го изпълним и го отворете с двойно щракване. Работи на 64-битови дистрибуции от около 2022 г. нататък.</p>',
    '>Download the AppImage</a>': '>Изтеглете AppImage</a>',
    '<span class="wip">work in progress</span>': '<span class="wip">в разработка</span>',
    '<p>Apple Silicon and Intel. Installed with Homebrew and a few Terminal commands.</p>':
        '<p>Apple Silicon и Intel. Инсталира се с Homebrew и няколко команди в Terminal.</p>',
    '>Install on macOS</a>': '>Инсталиране на macOS</a>',
    '<p>64-bit Windows 10 and 11. Installed with a few PowerShell commands.</p>':
        '<p>64-битови Windows 10 и 11. Инсталира се с няколко команди в PowerShell.</p>',
    '>Install on Windows</a>': '>Инсталиране на Windows</a>',
    '<p class="note">macOS and Windows support is new: if something doesn\'t work, or the instructions are unclear, please <a href="https://github.com/EdgarBarrantes/daRealKniga/issues/new/choose">tell us</a>. Feedback is much appreciated.</p>':
        '<p class="note">Поддръжката на macOS и Windows е нова: ако нещо не работи или указанията не са ясни, моля, <a href="https://github.com/EdgarBarrantes/daRealKniga/issues/new/choose">пишете ни</a>. Отзивите ви са много ценни.</p>',
    '<h2 id="use">Using it</h2>': '<h2 id="use">Как се използва</h2>',
    '<p>Open the window, drop in a document, pick the text language and press <strong>Make searchable</strong>. Or use the command line (<code>drk</code> is short for <code>darealkniga</code>):</p>':
        '<p>Отворете прозореца, пуснете документ, изберете езика на текста и натиснете <strong>Разпознай текста</strong>. Или използвайте командния ред (<code>drk</code> е кратката форма на <code>darealkniga</code>):</p>',
    '<td>A Bulgarian textbook with English in it</td>': '<td>Български учебник с английски текст</td>',
    '<td>A Bulgarian book, with its title and author stored in the PDF</td>': '<td>Българска книга; заглавието и авторът се записват в PDF файла</td>',
    '<td>A single photo: a receipt, a letter, a note</td>': '<td>Една снимка: касова бележка, писмо, бележка</td>',
    '<td>A folder of page photos, in page order</td>': '<td>Папка със снимки на страници, по ред</td>',
    '>Report a problem or suggest an idea</a> · MIT license': '>Съобщете за проблем или предложете идея</a> · лиценз MIT',
    '<p>Built on Tesseract, PaddleOCR, UVDoc and DjVuLibre.</p>': '<p>Изградена върху Tesseract, PaddleOCR, UVDoc и DjVuLibre.</p>',
}

T["fr"] = {
    '<title>daRealKniga</title>': '<title>daRealKniga — OCR pour les langues slaves</title>',
    'content="Free OCR for old books, archives and documents in Slavic languages and English: turns scans and phone photos into faithful, searchable PDFs, even when Cyrillic and Latin are mixed."':
        'content="OCR gratuit pour les livres anciens, les archives et les documents en langues slaves et en anglais : des scans et des photos au téléphone deviennent des PDF fidèles et interrogeables, même quand cyrillique et latin se mélangent."',
    'content="daRealKniga: OCR for Slavic and English documents"': 'content="daRealKniga : OCR pour les textes slaves et anglais"',
    'content="Scans and phone photos in, clean searchable PDFs out. Reads mixed Cyrillic and Latin text far better than plain OCR."':
        'content="Des scans et des photos au téléphone en entrée, des PDF propres et interrogeables en sortie. Lit le texte mêlant cyrillique et latin bien mieux qu’un OCR classique."',
    '<p class="tag">Turn old books, archives and everyday documents into faithful, <strong>searchable</strong> digital copies. Made for Slavic languages and English, even mixed on one page.</p>':
        '<p class="tag">Transformez livres anciens, archives et documents du quotidien en copies numériques fidèles et <strong>interrogeables</strong>. Conçu pour les langues slaves et l’anglais, même mélangés sur une même page.</p>',
    '<p class="gloss"><em>да</em> = yes, <em>книга</em> = book: “yes, a real book”, with real, searchable text.</p>':
        '<p class="gloss"><em>да</em> = oui, <em>книга</em> = livre : « oui, un vrai livre », avec un vrai texte, interrogeable.</p>',
    '>Get it, free</a>': '>Télécharger gratuitement</a>',
    '>How good is it?</a>': '>Quelle qualité ?</a>',
    '>Source on GitHub</a>': '>Code source sur GitHub</a>',
    'alt="A curled phone photo of a Bulgarian and English page is dropped into daRealKniga; a clean, searchable PDF comes out; plain OCR\'s misread words are shown next to daRealKniga\'s."':
        'alt="La photo courbée d’une page en bulgare et en anglais est déposée dans daRealKniga ; il en sort un PDF propre et interrogeable ; les erreurs d’un OCR classique sont montrées à côté du résultat de daRealKniga."',
    '<p class="caption">A real run: a phone photo in, a searchable PDF out, and plain OCR on the same photo for comparison.</p>':
        '<p class="caption">Une exécution réelle : une photo au téléphone en entrée, un PDF interrogeable en sortie et, pour comparer, un OCR classique sur la même photo (interface en anglais ; le logiciel existe aussi en français).</p>',
    '<h2 id="what">What it does</h2>': '<h2 id="what">Ce qu’il fait</h2>',
    '<h3>Searchable PDFs</h3><p>Turns DjVu books, image PDFs, photos and scans into PDFs you can search, select and copy. It also writes a plain text file and, for DjVu books, a searchable DjVu.</p>':
        '<h3>Des PDF interrogeables</h3><p>Transforme livres DjVu, PDF d’images, photos et scans en PDF où l’on peut chercher, sélectionner et copier le texte. Il écrit aussi un fichier texte brut et, pour les livres DjVu, un DjVu interrogeable.</p>',
    '<h3>Cyrillic and Latin, mixed</h3><p>Textbooks, dictionaries and bilingual documents keep each word in its own alphabet. Look-alike letters (<code>а</code>/<code>a</code>, <code>р</code>/<code>p</code>, <code>Н</code>/<code>H</code>) no longer break search.</p>':
        '<h3>Cyrillique et latin mélangés</h3><p>Dans les manuels, dictionnaires et documents bilingues, chaque mot garde son propre alphabet. Les lettres sosies (<code>а</code>/<code>a</code>, <code>р</code>/<code>p</code>, <code>Н</code>/<code>H</code>) ne cassent plus la recherche.</p>',
    '<h3>Photos, not just scans</h3><p>Curled, tilted, shadowed pages from a phone are flattened and cleaned up first, and every page ends up the same size.</p>':
        '<h3>Des photos, pas seulement des scans</h3><p>Les pages courbées, inclinées ou ombrées photographiées au téléphone sont d’abord redressées et nettoyées, et toutes les pages finissent au même format.</p>',
    '<h3>Your language, your computer</h3><p>The window comes in 31 languages, all Slavic ones included. Everything runs on your computer: your documents never leave it.</p>':
        '<h3>Votre langue, votre ordinateur</h3><p>L’interface existe en 31 langues, dont toutes les langues slaves. Tout fonctionne sur votre ordinateur : vos documents ne le quittent jamais.</p>',
    '<h2 id="books">For old books and archives</h2>': '<h2 id="books">Pour les livres anciens et les archives</h2>',
    '<p>daRealKniga is built for digitising whole books and collections, the way a library or an archive would want them: faithful to the original, consistent, and searchable.</p>':
        '<p>daRealKniga est conçu pour numériser des livres entiers et des collections comme le souhaiterait une bibliothèque ou un service d’archives : fidèles à l’original, cohérents et interrogeables.</p>',
    '<h3>The original stays intact</h3><p>DjVu scans keep their page images exactly as they are, with an invisible text layer added. A PDF and a plain-text file are written next to them.</p>':
        '<h3>L’original reste intact</h3><p>Les scans DjVu gardent leurs images de pages telles quelles ; seule une couche de texte invisible est ajoutée. Un PDF et un fichier texte brut sont écrits à côté.</p>',
    '<h3>Whole books, not just pages</h3><p>Hundreds of pages are processed in parallel. An interrupted run resumes where it stopped, and a page range lets you try the settings on a few pages first.</p>':
        '<h3>Des livres entiers, pas seulement des pages</h3><p>Des centaines de pages sont traitées en parallèle. Un traitement interrompu reprend là où il s’est arrêté, et une plage de pages permet d’essayer les réglages sur quelques pages d’abord.</p>',
    '<h3>Old print, uneven scans</h3><p>Every page ends up the same size, even when the scans don\'t match. Tested on Bulgarian and Russian editions from the 1970s, against their existing text.</p>':
        '<h3>Impressions anciennes, scans disparates</h3><p>Toutes les pages finissent au même format, même quand les scans diffèrent. Testé sur des éditions bulgares et russes des années 1970, par rapport à leur texte existant.</p>',
    '<h3>Catalogue-ready, and private</h3><p>Title and author are stored in the PDF. Everything runs on your own computer: collections never leave it, and the formats are open (PDF, DjVu, plain text).</p>':
        '<h3>Prêt pour le catalogue, et confidentiel</h3><p>Le titre et l’auteur sont enregistrés dans le PDF. Tout fonctionne sur votre ordinateur : les collections ne le quittent jamais, et les formats sont ouverts (PDF, DjVu, texte brut).</p>',
    '<h2 id="accuracy">Better than plain OCR</h2>': '<h2 id="accuracy">Meilleur qu’un OCR classique</h2>',
    '<p>Every sample is read three ways from the same page images: by Tesseract alone, by PaddleOCR alone, and by daRealKniga, which cleans the pages up, combines both engines word by word and corrects what they get wrong.</p>':
        '<p>Chaque échantillon est lu de trois façons à partir des mêmes images de pages : par Tesseract seul, par PaddleOCR seul et par daRealKniga, qui nettoie les pages, combine les deux moteurs mot par mot et corrige leurs erreurs.</p>',
    '<p class="note">The samples, the scoring and how to rerun it yourself are described in the <a href="https://github.com/EdgarBarrantes/daRealKniga#tests">README</a>.</p>':
        '<p class="note">Les échantillons, la notation et la façon de refaire le test vous-même sont décrits dans le <a href="https://github.com/EdgarBarrantes/daRealKniga#tests">README</a> (en anglais).</p>',
    '<h2 id="get-it">Get it</h2>': '<h2 id="get-it">Télécharger</h2>',
    '<p>Free and open source (MIT). The first run downloads the OCR models: about 45&nbsp;MB, plus 10–15&nbsp;MB per language.</p>':
        '<p>Gratuit et libre (MIT). Le premier lancement télécharge les modèles d’OCR : environ 45&nbsp;Mo, plus 10 à 15&nbsp;Mo par langue.</p>',
    '<p>A single file with everything included. Make it executable and double-click it. Works on 64-bit distributions from about 2022 on.</p>':
        '<p>Un seul fichier qui contient tout. Rendez-le exécutable et double-cliquez dessus. Fonctionne sur les distributions 64 bits depuis 2022 environ.</p>',
    '>Download the AppImage</a>': '>Télécharger l’AppImage</a>',
    '<span class="wip">work in progress</span>': '<span class="wip">en cours</span>',
    '<p>Apple Silicon and Intel. Installed with Homebrew and a few Terminal commands.</p>':
        '<p>Apple Silicon et Intel. S’installe avec Homebrew et quelques commandes dans le Terminal.</p>',
    '>Install on macOS</a>': '>Installer sur macOS</a>',
    '<p>64-bit Windows 10 and 11. Installed with a few PowerShell commands.</p>':
        '<p>Windows 10 et 11 en 64 bits. S’installe avec quelques commandes PowerShell.</p>',
    '>Install on Windows</a>': '>Installer sur Windows</a>',
    '<p class="note">macOS and Windows support is new: if something doesn\'t work, or the instructions are unclear, please <a href="https://github.com/EdgarBarrantes/daRealKniga/issues/new/choose">tell us</a>. Feedback is much appreciated.</p>':
        '<p class="note">La prise en charge de macOS et de Windows est récente : si quelque chose ne marche pas ou si les instructions ne sont pas claires, <a href="https://github.com/EdgarBarrantes/daRealKniga/issues/new/choose">dites-le-nous</a>. Vos retours sont très appréciés.</p>',
    '<h2 id="use">Using it</h2>': '<h2 id="use">Utilisation</h2>',
    '<p>Open the window, drop in a document, pick the text language and press <strong>Make searchable</strong>. Or use the command line (<code>drk</code> is short for <code>darealkniga</code>):</p>':
        '<p>Ouvrez la fenêtre, déposez-y un document, choisissez la langue du texte et cliquez sur <strong>Reconnaître le texte</strong>. Ou utilisez la ligne de commande (<code>drk</code> est la forme courte de <code>darealkniga</code>) :</p>',
    '<td>A Bulgarian textbook with English in it</td>': '<td>Un manuel bulgare avec de l’anglais</td>',
    '<td>A Bulgarian book, with its title and author stored in the PDF</td>': '<td>Un livre bulgare, avec le titre et l’auteur enregistrés dans le PDF</td>',
    '<td>A single photo: a receipt, a letter, a note</td>': '<td>Une seule photo : un ticket, une lettre, une note</td>',
    '<td>A folder of page photos, in page order</td>': '<td>Un dossier de photos de pages, dans l’ordre</td>',
    '>Report a problem or suggest an idea</a> · MIT license': '>Signaler un problème ou proposer une idée</a> · licence MIT',
    '<p>Built on Tesseract, PaddleOCR, UVDoc and DjVuLibre.</p>': '<p>Construit sur Tesseract, PaddleOCR, UVDoc et DjVuLibre.</p>',
}


def nav(lang):
    up = "" if lang == "en" else "../"
    links = []
    for code, name in LANGS.items():
        href = (up or "./") if code == "en" else f"{up}{code}/"
        cur = ' aria-current="page"' if code == lang else ""
        links.append(f'<a href="{href}" lang="{code}"{cur}>{name}</a>')
    return '<nav class="langs" aria-label="Language">' + "".join(links) + "</nav>"


def build(lang, english):
    s = english
    missing = [k for k in T[lang] if k not in s]
    if missing:
        sys.exit(f"{lang}: these English blocks are no longer on docs/index.html; update packaging/make_site.py:\n"
                 + "\n".join("  " + m[:100] for m in missing))
    for en, tr in T[lang].items():
        s = s.replace(en, tr)
    s = s.replace('<html lang="en">', f'<html lang="{lang}">')
    s = s.replace(nav("en"), nav(lang))
    for asset in ("style.css", "icon.png", "demo.gif"):
        s = s.replace(f'"{asset}"', f'"../{asset}"')
    return s


def main():
    english = open(os.path.join(DOCS, "index.html"), encoding="utf-8").read()
    if nav("en") not in english:
        sys.exit("docs/index.html has no language menu")
    for lang in T:
        os.makedirs(os.path.join(DOCS, lang), exist_ok=True)
        out = os.path.join(DOCS, lang, "index.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(build(lang, english))
        print("wrote", os.path.relpath(out, ROOT))
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import report
    run = report.load()
    if run:
        report.update_site(run)
        print("filled in the benchmark sections")


if __name__ == "__main__":
    main()
