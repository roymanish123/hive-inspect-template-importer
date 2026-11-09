# Input provenance

`residential-demo.html-text.csv` is **synthetic, original demonstration content**. It is not an export downloaded from Spectora, an InterNACHI template, or evidence of completing a trial. It contains no customer information. The file uses Spectora's documented spreadsheet column names and HTML-valued comment cells. It is the default seed and a runnable example, not a replacement for the assessment's required genuine export.

`edge-cases.html-text.csv` is an independently authored adversarial fixture: nontrivial ordering, repeated section names, Unicode, links, unsupported markup, continuation rows and extra metadata. `invalid-missing-parent.csv` demonstrates a blocked import.

Authoritative format references, consulted 9 November 2026:

- [Spectora export instructions](https://support.spectora.com/en/articles/2769896-how-to-export-a-template)
- [Spectora spreadsheet columns and ordering](https://support.spectora.com/en/articles/6198400-how-to-import-a-template-from-a-spreadsheet)
- [Spectora's published blank column-layout workbook](https://docs.google.com/spreadsheets/d/1gdMsUItVACbL4fq1Pqiie_u3xk_5UeMjPQTvhh1sMRU/edit)

Before assessment submission, add an actual shareable Spectora HTML-text export to this directory, record its template name/origin and SHA-256 here, test it with `python scripts/validate_export.py examples/your-file.xlsx`, and import it into the deployed app. A genuine export was not available in the supplied workspace or an authenticated session during this implementation. No source provenance has been invented.
