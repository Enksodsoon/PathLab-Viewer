# Login perspective artwork

`AuthPanel` loads one of the eight `auth-login-{theme}-{variant}-v2.png` files through a responsive `<picture>`. The light and dark sets use matching geometry for desktop, tablet landscape, tablet portrait, and mobile. PNG is retained to avoid visible JPEG blocking and banding.

The supplied **PathLab Login Asset Pack v1** (`Version 2/PathLab_Login_Asset_Pack_v1/assets/hero`) contains the source concept art. The source files are not copied into the application. The generated outputs are decorative concept art, not clinical imagery, and contain no patient data, labels, or UI text. The pack does not specify a separate license. The repository owner recorded approval for distribution of these eight exact v2 outputs in PathLab Viewer in [WARM_UI_IMAGE_APPROVAL.md](../../../../docs/supply-chain/WARM_UI_IMAGE_APPROVAL.md); this does not grant rights to unrelated artwork.

## Related source pack files

| Theme and variant | Source file | SHA-256 |
| --- | --- | --- |
| Light desktop | `hero-light-desktop-1920x1080.png` | `6ec47d2ec7f2617fb0d11bc062b7909929b5b929ddf8628b986a3099ab47de67` |
| Dark desktop | `hero-dark-desktop-1920x1080.png` | `9812079708719e10e07d2cbf8d421e43f431512769c8ad80f7bd8cf089f5547f` |
| Light tablet landscape | `hero-light-tablet-landscape-1366x1024.png` | `578cd9360fc8bb75ca4f37dcf27c1d4600b8c33fdcd3b3c7f4a431aff7ca909a` |
| Dark tablet landscape | `hero-dark-tablet-landscape-1366x1024.png` | `3c809d24863b40ad310af0511d8ebf4d3ffd67cd4bd1e3ec8faa5fbee93c2b7a` |
| Light tablet portrait | `hero-light-tablet-portrait-1024x1366.png` | `8260df232d118d42c2817122e8d303e367663f7fff15e92351f84d4a59f6cabd` |
| Dark tablet portrait | `hero-dark-tablet-portrait-1024x1366.png` | `903dc33aad3cf7984ea7a7b259c48f452bb3074f51461a50af59c8a5491e2429` |
| Light mobile | `hero-light-mobile-portrait-1080x1920.png` | `0b3c8103b88d75eae43673207fcb3b05b7cfffc54b3de6acb19eca62b0c05344` |
| Dark mobile | `hero-dark-mobile-portrait-1080x1920.png` | `972d4fd0ea1d12653b80500474eca7f99c2668702e74c4d439c48ebc132fcade` |

## Shipped outputs

| File | Generation source and dimensions | SHA-256 |
| --- | --- | --- |
| `auth-login-dark-desktop-v2.png` | Widescreen artwork, 1672×941 | `fa9c00d499374ac61ce08547e7ef2703559f475cb17b72a49e85c111a9895d86` |
| `auth-login-light-desktop-v2.png` | Widescreen artwork, 1672×941 | `60066497285db614bfa9bb9c3d0d67a61a3637fdba0953170e74b6ecc21ece64` |
| `auth-login-dark-tablet-landscape-v2.png` | Regenerated from supplied dark tablet artwork, 1448×1086 | `2fadd8040f2db9d698af6111350aa674bae4e8273ed746ec8a01020f09b841d1` |
| `auth-login-light-tablet-landscape-v2.png` | Regenerated from supplied light tablet artwork, 1448×1086 | `98d8e2a284d190c7d72c122a95acc7a9ac2176e4baed743c0cfcf666f5b8c2e6` |
| `auth-login-dark-mobile-v2.png` | Generated from dark tablet landscape v2, 941×1672 | `5a7c3464ddbcd0e5c918a8640ad0d388a97895f761e24385d2712eaddf4d4662` |
| `auth-login-light-mobile-v2.png` | Generated from light tablet landscape v2, 941×1672 | `4043f54f61f8116963fb5d05c7553a97de36541d328b0468c2b5af94868ee20a` |
| `auth-login-dark-tablet-portrait-v2.png` | Generated from dark mobile v2, 1086×1448 | `49f0bbf30da7797952eca7a8e09419b73364239bb55bcea90bb8f0ae900eb0a7` |
| `auth-login-light-tablet-portrait-v2.png` | Generated from light mobile v2, 1086×1448 | `ef36a95f8d72a937b101aced982a205217a37140f62a9a47ae5c4689576dfd0e` |

Existing PathLab fonts, icons, and live branding remain in use.
