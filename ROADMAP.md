# Roadmap

Ideas for future work, roughly in order of value. Contributions on any of them are welcome:
open an issue first to discuss the approach.

## Suggested next steps

1. **Latin words inside Cyrillic sentences.** Visible in the demo, measurable with the
   existing photo sample.
2. **ALTO XML and hOCR output.** What makes daRealKniga useful to libraries and archives.
3. **Packaged macOS and Windows apps,** once people start trying the source installs.

## Accuracy

- **Latin words inside Cyrillic sentences.** On the phone-photo sample, "Philippopolis" comes
  out in look-alike Cyrillic letters and the Roman numeral "II" becomes "ПП". Plain Tesseract
  reads both correctly, so the fusion turns a right word into a wrong one. This is likely the most
  visible remaining error on mixed pages. Reproduce with `python tests/accuracy.py photo-bg`, or
  see the last frame of `docs/demo.gif`.
- **Shadowed corners on photos.** The cleaned page from the phone photo keeps a grey gradient
  in its bottom-right corner. Cleanup should whiten it, or crop to the page edge.
- **Low-resolution scans.** The 133 dpi Bulgarian poems (`pdf-bg`) are the weakest sample, at
  88%, barely above plain OCR. Upscaling small text before OCR, or choosing settings per page
  from its resolution, could help a lot. Much archive material is scanned at low resolution.
- **Pre-reform spelling.** Old books use Russian spelling from before 1918 (ѣ, і, ѳ, ъ at word
  ends) and Bulgarian spelling from before 1945 (ѫ, ѣ). The dictionaries would currently
  "correct" those words into modern spelling. This needs a historical-spelling mode and a test
  sample from an old edition.

## For archivists and libraries

- **ALTO XML and hOCR output.** These are the standard OCR formats in libraries (Europeana,
  national libraries). Word positions are already available, so this is mostly a writer.
- **PDF/A output and richer metadata.** PDF/A is the archival PDF standard. Richer metadata
  would cover document language, year and publisher.
- **Batch processing.** A queue of books in the window, or `drk make collection/*.djvu`, with
  a summary report at the end (pages, word counts, low-confidence pages).
- **Proofreading view.** Show the words the engines disagreed on, next to the page image, and
  let people correct them before export. For important documents that must be near-perfect.

## Distribution

- **Ready-made macOS and Windows apps:** a `.dmg` and an installer, built in CI. This would
  remove the "work in progress" label and the Terminal/PowerShell steps.
- **Other channels:** PyPI (`pip install darealkniga`), Flathub, AUR and a Homebrew tap.
- **Smaller downloads.** The AppImage is about 530 MB; trimming unused Paddle and Qt parts
  could roughly halve it.

## Quality and community

- **Native-speaker review** of the 31 interface translations (`darealkniga/data/i18n/`) and of
  the project page in Russian, Bulgarian and French (`packaging/make_site.py`). A "translation
  review" issue per language would invite this.
- **More benchmark samples.** Ukrainian, Serbian, Macedonian and Polish have none yet. Real
  documents with hand-checked reference text would be more convincing than synthetic pages
  alone.
- **A scheduled CI run of the full accuracy suite** (for example weekly), so a regression or a
  change in a dependency shows up before a release.
- **Windows user names with non-Latin letters.** The model cache lives in the user folder; a
  Cyrillic user name puts it on a path that Tesseract may still fail to open.
