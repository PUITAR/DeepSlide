The following are the usage guidelines for the DeepSlide template; please strictly adhere to them:

1. base.tex  
- Type: File
- Purpose: Global template style definition file.  
- Forbidden: Writing main text directly here; arbitrarily deleting or modifying existing layout commands.  
- Recommendation: If you need to adjust headers, footers, theme colors, or font sizes, do so here to keep the entire slide deck consistent.

2. content.tex
- Type: File
- Purpose: The sole entry point for slide content.  
- Forbidden: Piling up large blocks of formulas or figure code.  
- Recommendation: Split logic by sections; keep each section to no more than 10 lines of main text.

3. ref.bib  
- Type: File
- Purpose: Central bibliography data source.  
- Forbidden: Fabricating reference entries; using non-standard BibTeX entry types.  
- Recommendation: Add each new reference to this file immediately.

4. picture/  
- Type: Directory
- Purpose: Root directory for all image assets.  
- Forbidden: Placing images in the root or any other custom folder; using Chinese or special symbols in image filenames.  
- Recommendation: Adjust images appropriately to ensure slide aesthetics after compilation.

5. title.tex
- Type: File
- Purpose: Title slide content.  
- Forbidden: Modifying title, author, or institute commands.  
- Recommendation: Customize title, subtitle, author, and institute information here.
