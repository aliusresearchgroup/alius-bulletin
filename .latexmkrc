# ALIUS Bulletin uses native reconstructed layouts with system/OpenType fonts.
# Overleaf sometimes defaults to pdfLaTeX; force latexmk to use LuaLaTeX so
# the visual reconstruction path remains the default and most faithful build.
$pdf_mode = 4;
$pdflatex = 'lualatex -interaction=nonstopmode -file-line-error -synctex=1 %O %S';
$lualatex = 'lualatex -interaction=nonstopmode -file-line-error -synctex=1 %O %S';
