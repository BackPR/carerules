# Credits and licenses

CareRules is an individual entry by MohammadMahdi RezaAli to the Hugging Face x Reflection "Build with Beam" challenge, published by BackPR.

## What our licenses cover

- **Code** (everything in `carerules/`, `scripts/`, `static/*.js`, `static/*.css`, `static/index.html`, `worker/`): Apache License 2.0, see [LICENSE](LICENSE).
- **Data we created** (`data/checklists/`, `data/gold/`, `samples/`, `results/`): CC BY 4.0. The checklists and the suggested wording in the results were written by Beam 1.0; the question answer key and the test handbooks were written with AI help and checked by code, not by a lawyer.

## Third-party content (not covered by our licenses)

- **State licensing rules** (`text/*.txt`; `rulebooks/` in the dataset): official government documents, each downloaded once from the official URL listed in `data/sources.json` on October 28, 2026. They are included so the tool can check quotes word for word, and each publisher's own terms apply, not ours. Some publishers state copyright or reuse terms, for example: Pennsylvania ("Copyright Commonwealth of Pennsylvania", printed on the rule pages), Georgia (rules.sos.ga.gov, hosted by Fastcase), Virginia (Legislative Information System), Washington (Statute Law Committee) and Colorado (Secretary of State). Please don't use these texts to train models, and check each source's terms before reusing them. If you're a rights holder with a concern, email hi@backpr.com and we'll remove the text.
- **Beam 1.0** by Reflection (Apache License 2.0): https://huggingface.co/reflection/Beam-1.0-501B-A23B. Use of CareRules follows Reflection's Usage Policy: https://reflection.ai/legal/usage-policy.
- **Photos** (`static/media/*.jpg` except `og.jpg` and `report-shot.jpg`, which we made): Unsplash, under the Unsplash License (https://unsplash.com/license). Sources:
  - `hero-documents.jpg`: https://images.unsplash.com/photo-1775163024488-e88e4a71179f
  - `director.jpg`: https://images.unsplash.com/photo-1758876201660-103984519266
  - `nap-room.jpg`: https://images.unsplash.com/photo-1774578342155-8d7e44a18bfd
  - `lunch-table.jpg`: https://images.unsplash.com/photo-1777056481869-feac70afe522
  - `classroom.jpg`: https://images.unsplash.com/photo-1761208663763-c4d30657c910
  - `teachers.jpg`: https://images.unsplash.com/photo-1786292949404-084cbd10c7b1
  - `new-center.jpg`: https://images.unsplash.com/photo-1567746512136-f005499a7575
  - `kids-table.jpg`: https://images.unsplash.com/photo-1777056491418-d4ff81a4ad92
  - `park.jpg`: https://images.unsplash.com/photo-1627764940620-90393d0e8c34
  - `screen-time.jpg`: https://images.unsplash.com/photo-1505976442149-53a82393903b
  - `visiting-dog.jpg`: https://images.unsplash.com/photo-1609271460901-a354fca155a0

  The people in these photos have no connection to CareRules or BackPR and don't endorse them.
- **Demo video** (`static/media/carerules-demo.mp4` and `.gif`; source in `video/demo/`, rendered with HyperFrames): made by us. The handbook sentence is from our made-up sample handbook; the rule text is quoted from Texas HHSC's Minimum Standards (see State licensing rules above).
- **Hero video** on care.backpr.com: a Mixkit clip used on the website under Mixkit's license. It is not included in this repository or the Space.
- **Fonts** (`static/fonts/`): Hepta Slab and Inter, SIL Open Font License 1.1 (`static/fonts/OFL-HeptaSlab.txt`, `static/fonts/OFL-Inter.txt`).
- **Libraries loaded by the page from cdnjs** (not included here): pdf.js 4.10.38 (Apache License 2.0) and mammoth 1.8.0 (BSD 2-Clause).
- **BackPR** name and logo (`static/media/brand/`, `video/demo/assets/backpr-logo-white.svg`): trademarks of BackPR, not licensed under Apache 2.0 or CC BY.
