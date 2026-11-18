# Notebook Han webfont

Chinese handwriting for the shared notebook theme.

- Upstream: [Xiaolai by LXGW](https://github.com/lxgw/kose-font), version 3.126.
- Source: https://github.com/lxgw/kose-font/releases/download/v3.126/Xiaolai-Regular.ttf
- Source SHA-256: e2f68daf0e72777a8cf58bc83de1b98634b251e537ddbfca24b0ae50d1802da2
- License: SIL Open Font License 1.1; the original notice is in OFL-Xiaolai.txt.
- This WOFF2 subset keeps Chinese ideographs, radicals and CJK punctuation. The
  family is renamed Notebook Han because the upstream reserves its font names.
- Latin glyphs are excluded so the existing English handwriting stays in use.
- 29765 code points, 8509516 bytes; built with fontTools and Brotli.
- All 942 Chinese characters currently used in the frontend and backend source are covered.
- Served locally from the application; no third-party font request is needed.

The smaller NotebookHan-Common.woff2 contains GB2312 characters, CJK punctuation and all Chinese characters currently used by this project. It is preloaded once and preferred by handwriting.css; the larger face is loaded only for additional characters. Both faces exclude Latin glyphs.

The two faces have disjoint Unicode ranges so common text never requests the extended font. Additional rare or traditional characters load the extended face on demand.
