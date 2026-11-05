# fal.ai model catalog snapshot

Generated: 2026-11-05 by `falg catalog` (released since 2026-05-09; categories: text-to-image, image-to-image).

> **Don't pick models from memory**: names and versions change every month. Use this
> file if it is fresh (under 30 days old); otherwise run `falg catalog` first.
> Check an endpoint's inputs with `falg schema <endpoint>` before adding it to the registry.

Prices come from fal's pricing API, as reported (`unit` varies: per image, per
megapixel, or fal's generic `units`). Confirm on the model page before relying on them.

## Registry check

These are the models falg knows (`src/falg/models.json`). The last column lists newer
catalog entries from the same family; consider upgrading to them.

| registry name          | mode     | endpoint                                      | released   | price               | newer in family                                                                                                                                                                                         |
| ---------------------- | -------- | --------------------------------------------- | ---------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| seedream-5-pro         | generate | `bytedance/seedream/v5/pro/text-to-image`     | 2026-07-07 | $0.0675 / units     | `bytedance/seedream/v5/flash/text-to-image` (2026-09-23), `bytedance/seedream/v5/lite/text-to-image` (2026-07-08)                                                                                       |
| seedream-5-pro         | edit     | `bytedance/seedream/v5/pro/edit`              | 2026-07-07 | $0.0675 / units     | `bytedance/seedream/v5/flash/layerize` (2026-09-23), `bytedance/seedream/v5/flash/edit` (2026-09-23), `bytedance/seedream/v5/pro/layerize` (2026-08-06), `bytedance/seedream/v5/lite/edit` (2026-07-08) |
| flux-3                 | generate | `blackforestlabs/flux-3/text-to-image`        | 2026-10-01 | $0.048 / megapixels | `blackforestlabs/flux-3/klein/text-to-image/lora` (2026-10-26), `blackforestlabs/flux-3/klein/base/text-to-image/lora` (2026-10-26), `blackforestlabs/flux-3/klein/text-to-image` (2026-10-14)          |
| flux-3                 | edit     | `blackforestlabs/flux-3/edit-image`           | 2026-10-01 | $0.048 / megapixels | `blackforestlabs/flux-3/klein/edit-image/lora` (2026-10-26), `blackforestlabs/flux-3/klein/base/edit-image/lora` (2026-10-26), `blackforestlabs/flux-3/klein/edit-image` (2026-10-14)                   |
| nano-banana-2.1        | generate | `google/nano-banana-2.1`                      | 2026-10-06 | $1 / units          |                                                                                                                                                                                                         |
| nano-banana-2.1        | edit     | `google/nano-banana-2.1/edit`                 | 2026-10-06 | $1 / units          |                                                                                                                                                                                                         |
| gpt-image-2.5          | generate | `openai/gpt-image-2.5/flare/text-to-image`    | 2026-09-08 | $1 / units          | `openai/gpt-image-2.6/sunburst/text-to-image` (2026-11-04), `openai/gpt-image-2.6/flare/text-to-image` (2026-11-04)                                                                                     |
| gpt-image-2.5          | edit     | `openai/gpt-image-2.5/flare/edit`             | 2026-09-08 | $1 / units          | `openai/gpt-image-2.6/sunburst/edit` (2026-11-04), `openai/gpt-image-2.6/flare/edit` (2026-11-04)                                                                                                       |
| gpt-image-2.6          | generate | `openai/gpt-image-2.6/flare/text-to-image`    | 2026-11-04 | $1 / units          |                                                                                                                                                                                                         |
| gpt-image-2.6          | edit     | `openai/gpt-image-2.6/flare/edit`             | 2026-11-04 | $1 / units          |                                                                                                                                                                                                         |
| gpt-image-2.6-sunburst | generate | `openai/gpt-image-2.6/sunburst/text-to-image` | 2026-11-04 | $1 / units          |                                                                                                                                                                                                         |
| gpt-image-2.6-sunburst | edit     | `openai/gpt-image-2.6/sunburst/edit`          | 2026-11-04 | $1 / units          |                                                                                                                                                                                                         |
| gpt-image-2.5-sunburst | generate | `openai/gpt-image-2.5/sunburst/text-to-image` | 2026-09-08 | $1 / units          | `openai/gpt-image-2.6/sunburst/text-to-image` (2026-11-04), `openai/gpt-image-2.6/flare/text-to-image` (2026-11-04)                                                                                     |
| nano-banana-pro        | generate | `fal-ai/nano-banana-pro`                      | 2025-11-20 | $0.15 / images      |                                                                                                                                                                                                         |
| nano-banana-pro        | edit     | `fal-ai/nano-banana-pro/edit`                 | 2025-11-20 | $0.15 / images      |                                                                                                                                                                                                         |
| seedream-5-lite        | generate | `bytedance/seedream/v5/lite/text-to-image`    | 2026-07-08 | $0.035 / images     | `bytedance/seedream/v5/flash/text-to-image` (2026-09-23)                                                                                                                                                |
| seedream-5-flash       | generate | `bytedance/seedream/v5/flash/text-to-image`   | 2026-09-23 | $0.027 / images     |                                                                                                                                                                                                         |
| ideogram-4.5           | generate | `ideogram/v4.5`                               | 2026-09-30 | $0.001 / units      | `ideogram/vector/text-to-vector` (2026-10-22)                                                                                                                                                           |
| recraft-vector         | generate | `fal-ai/recraft/v4.1/pro/text-to-vector`      | 2026-05-14 | $0.3 / images       | `recraft/v4.1/flash/text-to-image` (2026-09-20), `recraft/v4/style/pro/text-to-vector` (2026-08-26), `recraft/v4/style/pro/text-to-image` (2026-08-26), `recraft/v4/style/text-to-vector` (2026-08-26)  |

## text-to-image: 52 released since 2026-05-09

| released   | endpoint                                               | name                                 | price               | in registry |
| ---------- | ------------------------------------------------------ | ------------------------------------ | ------------------- | ----------- |
| 2026-11-04 | `openai/gpt-image-2.6/sunburst/text-to-image`          | GPT Image 2.6 Sunburst Text to Image | $1 / units          | yes         |
| 2026-11-04 | `openai/gpt-image-2.6/flare/text-to-image`             | GPT Image 2.6 Flare Text to Image    | $1 / units          | yes         |
| 2026-10-26 | `blackforestlabs/flux-3/klein/text-to-image/lora`      | FLUX 3 Klein Text to Image LoRA      | $0.012 / megapixels |             |
| 2026-10-26 | `blackforestlabs/flux-3/klein/base/text-to-image/lora` | FLUX 3 Klein Base Text to Image LoRA | $0.035 / megapixels |             |
| 2026-10-22 | `ideogram/vector/text-to-vector`                       | Ideogram Vector                      | $0.01 / units       |             |
| 2026-10-19 | `bria/fibo-2/generate`                                 | Fibo 2.0 Generate                    | $0.04 / images      |             |
| 2026-10-18 | `fal-ai/moss-image`                                    | MOSS Image                           | $0.05 / megapixels  |             |
| 2026-10-14 | `krea/v3/text-to-image`                                | Krea 3 Text to Image                 | $0.025 / megapixels |             |
| 2026-10-14 | `blackforestlabs/flux-3/klein/text-to-image`           | FLUX.3 Klein                         | $0.009 / megapixels |             |
| 2026-10-06 | `google/nano-banana-2.1`                               | Nano Banana 2.1                      | $1 / units          | yes         |
| 2026-10-01 | `blackforestlabs/flux-3/text-to-image`                 | Flux 3 Image                         | $0.048 / megapixels | yes         |
| 2026-09-30 | `ideogram/v4.5`                                        | Ideogram V4.5 Text to Image          | $0.001 / units      | yes         |
| 2026-09-23 | `bytedance/seedream/v5/flash/text-to-image`            | Seedream                             | $0.027 / images     | yes         |
| 2026-09-20 | `recraft/v4.1/flash/text-to-image`                     | Recraft V4.1 Flash Text to Image     | $0.007 / images     |             |
| 2026-09-08 | `openai/gpt-image-2.5/sunburst/text-to-image`          | GPT Image 2.5 Sunburst Text to Image | $1 / units          | yes         |
| 2026-09-08 | `openai/gpt-image-2.5/flare/text-to-image`             | GPT Image 2.5 Flare Text to Image    | $1 / units          | yes         |
| 2026-08-26 | `recraft/v4/style/pro/text-to-vector`                  | Recraft V4 Styles Pro Text to Vector | $0.12 / images      |             |
| 2026-08-26 | `recraft/v4/style/pro/text-to-image`                   | Recraft V4 Styles Pro Text to Image  | $0.1 / images       |             |
| 2026-08-26 | `recraft/v4/style/text-to-vector`                      | Recraft V4 Styles Text to Vector     | $0.05 / images      |             |
| 2026-08-26 | `recraft/v4/style/text-to-image`                       | Recraft V4 Styles Text to Image      | $0.035 / images     |             |
| 2026-08-21 | `meta/muse-image/text-to-image`                        | Meta Muse Image Text to Image        | $0.01 / images      |             |
| 2026-08-18 | `bria/fibo-gen-1.5/text-to-image`                      | Fibo Gen 1.5 Text to Image           | $0.04 / images      |             |
| 2026-08-06 | `xai/grok-imagine-image/v2.0/text-to-image`            | Grok Imagine Image 2.0               | $0.01 / units       |             |
| 2026-07-28 | `microsoft/mai-image-2.5-pro`                          | MAI Image 2.5 Pro (Text to Image)    | $1.5 / credits      |             |
| 2026-07-21 | `alibaba/qwen-image-3/text-to-image`                   | Qwen Image 3 Text to Image           | $0.01 / units       |             |
| 2026-07-10 | `fal-ai/krea-2/turbo/style`                            | Krea 2 Text to Image Turbo Style     | $0.01 / megapixels  |             |
| 2026-07-08 | `bytedance/seedream/v5/lite/text-to-image`             | Seedream                             | $0.035 / images     | yes         |
| 2026-07-07 | `bytedance/seedream/v5/pro/text-to-image`              | Seedream 5.0 Pro Text to Image       | $0.0675 / units     | yes         |
| 2026-07-06 | `ideogram/v4/instant`                                  | V4.0q [instant]                      | $0.005 / units      |             |
| 2026-07-03 | `ideogram/v4/fast`                                     | V4.0q [fast]                         | $0.007 / units      |             |
| 2026-06-30 | `google/nano-banana-2-lite`                            | Nano Banana 2 Lite                   | $1 / units          |             |
| 2026-06-30 | `google/nano-banana-lite`                              | Nano Banana Lite                     | $1 / units          |             |
| 2026-06-19 | `fal-ai/krea-2/turbo/lora`                             | Krea 2 Text to Image Turbo LoRA      | $0.01 / megapixels  |             |
| 2026-06-18 | `fal-ai/krea-2/turbo`                                  | Krea 2 Turbo                         | $0.008 / megapixels |             |
| 2026-06-18 | `fal-ai/boogu-image`                                   | Boogu Image                          | $0.04 / megapixels  |             |
| 2026-06-09 | `luma/agent/uni-1/v1/text-to-image`                    | Luma Uni-1 Text to Image             | $0.003 / images     |             |
| 2026-06-09 | `luma/agent/uni-1/v1/max`                              | Luma Uni-1 Text to Image Max         | $0.003 / images     |             |
| 2026-06-08 | `ideogram/v4/lora`                                     | Ideogram V4.0q Text to Image (LoRA)  | $0.015 / units      |             |
| 2026-06-03 | `krea/v2/medium/turbo/text-to-image`                   | Krea 2 Medium Text to Image Turbo    | $0.001 / units      |             |
| 2026-06-02 | `microsoft/mai-image-2.5`                              | Mai Image 2.5 Text to Image          | $1 / credits        |             |
| 2026-06-02 | `ideogram/v4`                                          | Ideogram V4.0 Text to Image          | $0.01 / units       |             |
| 2026-06-01 | `nvidia/cosmos-3-super/text-to-image`                  | Cosmos 3 Super                       | $0.04 / images      |             |
| 2026-05-27 | `krea/v2/medium/text-to-image`                         | Krea 2 Medium                        | $0.001 / units      |             |
| 2026-05-27 | `krea/v2/large/text-to-image`                          | Krea 2 Large                         | $0.001 / units      |             |
| 2026-05-14 | `fal-ai/recraft/v4.1/utility/text-to-image`            | Recraft V4.1 Text to Image Utility   | $0.035 / images     |             |
| 2026-05-14 | `fal-ai/recraft/v4.1/utility/pro/text-to-image`        | Recraft V4.1 Utility Text to Image   | $0.21 / images      |             |
| 2026-05-14 | `fal-ai/recraft/v4.1/text-to-vector`                   | Recraft V4.1 Text to Vector          | $0.08 / images      |             |
| 2026-05-14 | `fal-ai/recraft/v4.1/text-to-image`                    | Recraft V4.1 Text to Image           | $0.035 / images     |             |
| 2026-05-14 | `fal-ai/recraft/v4.1/pro/text-to-vector`               | Recraft V4.1 Text to Vector Pro      | $0.3 / images       | yes         |
| 2026-05-14 | `fal-ai/recraft/v4.1/pro/text-to-image`                | Recraft V4.1 Text to Image Pro       | $0.21 / images      |             |
| 2026-05-09 | `fal-ai/hidream-o1-image`                              | Hidream O1 Image                     | $0.01 / megapixels  |             |
| 2026-05-09 | `fal-ai/hidream-o1-image/dev`                          | Hidream O1 Image                     | $0.005 / megapixels |             |

## image-to-image: 62 released since 2026-05-09

| released   | endpoint                                            | name                                                                          | price                         | in registry |
| ---------- | --------------------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------- | ----------- |
| 2026-11-04 | `openai/gpt-image-2.6/sunburst/edit`                | GPT Image 2.6 Sunburst Edit                                                   | $1 / units                    | yes         |
| 2026-11-04 | `openai/gpt-image-2.6/flare/edit`                   | GPT Image 2.6 Flare Edit                                                      | $1 / units                    | yes         |
| 2026-10-26 | `blackforestlabs/flux-3/klein/edit-image/lora`      | FLUX 3 Klein Edit LoRA                                                        | $0.012 / megapixels           |             |
| 2026-10-26 | `blackforestlabs/flux-3/klein/base/edit-image/lora` | FLUX 3 Klein Base Edit LoRA                                                   | $0.035 / megapixels           |             |
| 2026-10-22 | `ideogram/vector/image-to-vector`                   | Ideogram Vector                                                               | $0.01 / units                 |             |
| 2026-10-19 | `bria/fibo-2/edit`                                  | Fibo 2.0 Edit                                                                 | $0.04 / images                |             |
| 2026-10-14 | `krea/v3/realtime`                                  | Krea 3 Realtime                                                               | $0.013 / seconds              |             |
| 2026-10-14 | `krea/v3/edit`                                      | Krea 3 Edit                                                                   | $0.025 / megapixels           |             |
| 2026-10-14 | `blackforestlabs/flux-3/klein/edit-image`           | FLUX.3 Klein Image Editing                                                    | $0.009 / megapixels           |             |
| 2026-10-10 | `bria/fibo-edit-1.5/expand`                         | Bria Expand (FIBO-Edit-1.5)                                                   | $0.04 / images                |             |
| 2026-10-10 | `bria/guided-remove-background`                     | Bria Guided Remove Background                                                 | $0.03 / images                |             |
| 2026-10-06 | `google/nano-banana-2.1/edit`                       | Nano Banana 2.1 Edit                                                          | $1 / units                    | yes         |
| 2026-10-02 | `fal-ai/marigold-v2`                                | Marigold V2 Depth                                                             | $0.03 / images                |             |
| 2026-10-01 | `blackforestlabs/flux-3/edit-image`                 | Flux 3 Image                                                                  | $0.048 / megapixels           | yes         |
| 2026-09-30 | `ideogram/v4.5/edit`                                | Ideogram V4.5 Edit                                                            | $0.001 / units                |             |
| 2026-09-23 | `bytedance/seedream/v5/flash/layerize`              | Seedream                                                                      | $0.027 / images               |             |
| 2026-09-23 | `bytedance/seedream/v5/flash/edit`                  | Seedream                                                                      | $0.027 / images               |             |
| 2026-09-17 | `bria/fibo-edit-1.5/virtual-try-on`                 | Bria Virtual Try-On (FIBO-Edit-1.5)                                           | $0.04 / images                |             |
| 2026-09-17 | `bria/fibo-edit-1.5/product-holding`                | Bria Product Holding (FIBO-Edit-1.5)                                          | $0.04 / images                |             |
| 2026-09-08 | `openai/gpt-image-2.5/sunburst/edit`                | GPT Image 2.5 Sunburst Edit                                                   | $1 / units                    |             |
| 2026-09-08 | `openai/gpt-image-2.5/flare/edit`                   | GPT Image 2.5 Flare Edit                                                      | $1 / units                    | yes         |
| 2026-09-07 | `bria/increase-resolution`                          | Bria Increase Resolution: Upscale Images up to 4x Without Losing Detail / fal | $0.04 / images                |             |
| 2026-08-24 | `google/virtual-try-on`                             | Google Virtual Try On                                                         | $0.075 / images               |             |
| 2026-08-21 | `meta/muse-image/edit`                              | Meta Muse Image Edit                                                          | $0.01 / images                |             |
| 2026-08-18 | `bria/fibo-edit-1.5/edit`                           | Fibo Edit 1.5 Image Editing                                                   | $0.04 / images                |             |
| 2026-08-11 | `topaz/upscale/image/generative`                    | Topaz Upscale Image Generative                                                | $0.01 / units                 |             |
| 2026-08-11 | `topaz/sharpen/image`                               | Topaz Sharpen Image                                                           | $0.01 / units                 |             |
| 2026-08-11 | `topaz/denoise/image`                               | Topaz Denoise Image                                                           | $0.01 / units                 |             |
| 2026-08-11 | `topaz/restore/image`                               | Topaz Restore Image                                                           | $0.01 / units                 |             |
| 2026-08-11 | `topaz/upscale/image/transparent`                   | Topaz Upscale Image Transparent                                               | $0.01 / units                 |             |
| 2026-08-11 | `topaz/upscale/image/creative`                      | Topaz Upscale Image Creative                                                  | $0.01 / units                 |             |
| 2026-08-11 | `topaz/upscale/image/precision`                     | Topaz Upscale Image Precision                                                 | $0.01 / units                 |             |
| 2026-08-11 | `topaz/adjust/image`                                | Topaz Adjust Image                                                            | $0.01 / units                 |             |
| 2026-08-06 | `bytedance/seedream/v5/pro/layerize`                | Seedream 5.0 Pro Layerize                                                     | $0.03375 / images             |             |
| 2026-08-06 | `xai/grok-imagine-image/v2.0/edit`                  | Grok Imagine Image 2.0                                                        | $0.01 / units                 |             |
| 2026-07-31 | `hitem3d/hi3d/image-to-relief`                      | Hi3D Image to Relief                                                          | $0.02 / credits               |             |
| 2026-07-29 | `fal-ai/ideogram/object-removal`                    | Ideogram Object Removal                                                       | $0.03 / images                |             |
| 2026-07-28 | `microsoft/mai-image-2.5-pro/edit`                  | MAI Image 2.5 Pro (Edit)                                                      | $1.5 / credits                |             |
| 2026-07-28 | `fal-ai/feynobg`                                    | Feynobg Background Remover                                                    | $0.001 / generations          |             |
| 2026-07-28 | `pixelcut/product-photo`                            | Pixelcut Product Photo                                                        | $0.024 / images               |             |
| 2026-07-21 | `alibaba/qwen-image-3/edit`                         | Qwen Image 3 Image Editing                                                    | $0.01 / units                 |             |
| 2026-07-13 | `bria/product-dimensions`                           | Bria Product Dimensions                                                       | $0.04 / images                |             |
| 2026-07-08 | `bytedance/seedream/v5/lite/edit`                   | Seedream                                                                      | $0.035 / images               |             |
| 2026-07-07 | `bytedance/seedream/v5/pro/edit`                    | Seedream 5.0 Pro Image Editing                                                | $0.0675 / units               | yes         |
| 2026-06-30 | `google/nano-banana-lite/edit`                      | Nano Banana Lite Edit                                                         | $1 / units                    |             |
| 2026-06-28 | `bria/extract-object`                               | Extract Object                                                                | $0.02 / images                |             |
| 2026-06-22 | `fal-ai/telestyle-v2`                               | Telestyle V2 Style Transfer                                                   | $0.035 / megapixels           |             |
| 2026-06-18 | `fal-ai/boogu-image/edit`                           | Boogu Image                                                                   | $0.04 / megapixels            |             |
| 2026-06-10 | `ideogram/v4/tiling/lora`                           | Ideogram V4.0q Tiling LoRA                                                    | $0.045 / images               |             |
| 2026-06-10 | `ideogram/v4/tiling`                                | Ideogram V4.0q Tiling                                                         | $0.04 / images                |             |
| 2026-06-10 | `ideogram/v4/image-to-image/lora`                   | Ideogram V4.0q Image to Image LoRA                                            | $0.015 / units                |             |
| 2026-06-10 | `ideogram/v4/image-to-image`                        | Ideogram V4.0q Image to Image                                                 | $0.01 / units                 |             |
| 2026-06-09 | `luma/agent/uni-1/v1/max/edit`                      | Luma Uni-1 Edit Max                                                           | $0.003 / images               |             |
| 2026-06-09 | `luma/agent/uni-1/v1/edit`                          | Luma Uni-1 Edit                                                               | $0.003 / images               |             |
| 2026-06-08 | `bria/genfill/v2`                                   | Genfill                                                                       | $0.04 / megapixels            |             |
| 2026-06-03 | `microsoft/mai-image-2.5/edit`                      | Mai Image 2.5                                                                 | $1 / credits                  |             |
| 2026-05-27 | `fal-ai/flux-pro/v1/vto`                            | FLUX Virtual Try-On                                                           | $0.005 / processed megapixels |             |
| 2026-05-27 | `fal-ai/control-light`                              | ControlLight                                                                  | $0.03 / megapixels            |             |
| 2026-05-21 | `fal-ai/flux-pro/v1/erase`                          | Flux Pro Erase                                                                | $0.004 / megapixels           |             |
| 2026-05-14 | `fal-ai/flux-2-pro/outpaint`                        | FLUX 2 Pro Outpaint                                                           | $0.03 / processed megapixels  |             |
| 2026-05-09 | `fal-ai/hidream-o1-image/dev/edit`                  | Hidream O1 Image                                                              | $0.005 / megapixels           |             |
| 2026-05-09 | `fal-ai/hidream-o1-image/edit`                      | Hidream O1 Image                                                              | $0.01 / megapixels            |             |
