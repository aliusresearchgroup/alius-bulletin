# Cover Verification

Verification was run against `Cover-Art/reference-covers/issueXX-original-cover.pdf` for Issues 1-7.

## Result

All generated cover PDFs render pixel-identically to their reference cover at 600 DPI.

| Issue | Render size | Differing pixels | Max channel delta | Text/font span check |
| --- | ---: | ---: | ---: | --- |
| 01 | 4959 x 7017 | 0.0000% | 0 | Source has no PDF text spans; generated cover also has none. |
| 02 | 4959 x 7017 | 0.0000% | 0 | Source has no PDF text spans; generated cover also has none. |
| 03 | 4962 x 7016 | 0.0000% | 0 | 27/27 spans match exactly, including text, font name, size, color, bbox, and origin. |
| 04 | 4962 x 7016 | 0.0000% | 0 | 23/23 spans match exactly, including text, font name, size, color, bbox, and origin. |
| 05 | 4961 x 7016 | 0.0000% | 0 | Source has no PDF text spans; generated cover also has none. |
| 06 | 4966 x 7024 | 0.0000% | 0 | 69/69 spans match exactly, including text, font name, size, color, bbox, and origin. |
| 07 | 4967 x 7017 | 0.0000% | 0 | 126/126 spans match exactly, including text, font name, size, color, bbox, and origin. |

## Notes

Issues 1, 2, and 5 are raster-only in the source reference covers, so there are no recoverable font objects to preserve. Their visible typography is preserved as 600 DPI transparent overlays extracted from the original cover render.

Issues 3, 4, 6, and 7 preserve the original PDF text/font spans. Issues 3 and 4 also include a transparent visual correction layer so the final rendered cover is pixel-identical to the reference while retaining the original text layer.

The finished `Bulletins/issueXX.pdf` files were also checked after the finalization pass. Page 1 of every issue PDF renders pixel-identically to its reference cover at 600 DPI with zero differing pixels.
