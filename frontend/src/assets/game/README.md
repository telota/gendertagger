# Archive otter artwork

`archive-otter.png` is a transparent 1944 × 809 PNG atlas generated with the built-in image generation
tool on 2026-09-26 for the optional game mode. Its three poses are rest, stamp, and complete.
`ArchiveOtter.vue` displays one cell at a time. The original generated alpha channel is preserved;
the asset has no semantic meaning and is hidden from assistive technology. No new runtime dependency
is required.

## Generation prompt

```text
Use case: illustration-story.
Asset type: ONE transparent sprite-sheet PNG for a scholarly web game's small archive-otter companion. A single wide canvas divided into exactly THREE equal square cells horizontally, each holding one pose of the SAME original otter at the SAME scale and baseline. Transparent alpha background, no backdrop, no ground shadow, no cell borders, no text.
Primary request: a really lovable original otter with Disney-like classic storybook character appeal, illustrated as sophisticated handmade cut-paper collage. Big warm expressive dark eyes, small rounded ears, plump cream muzzle, tiny dark nose, delicate whiskers, warm chestnut brown fur, soft cream tummy, endearing rounded proportions and small paws. Layered torn paper edges and subtly printed paper fibers, painted gouache details, gentle dimensional overlaps. Charming polished character art, not a flat vector icon, not photoreal or plastic 3D.
Palette: warm cinnamon/chestnut, honey cream, muted violet stationery accents. Keep the silhouette bold and face readable when a cell is displayed at 80px.
Composition: three equally spaced centered full-body otters, generous transparent padding in each cell, nothing crosses between cells. Each character fits inside its cell with all tail, ears and props visible.
LEFT CELL: quiet attentive otter facing the viewer, sitting upright, both paws resting near the bottom of its belly, a tiny violet paper bookmark tucked against the tummy.
MIDDLE CELL: same otter leaning slightly forward with one paw pressing a small violet wooden rubber stamp down at its feet, pleased gentle expression.
RIGHT CELL: same otter sitting contentedly holding a little cream library ticket in its paws, wearing tiny round violet reading glasses. Ticket has a few simple decorative ink strokes only, no letters.
Constraints: original character, consistent face and body in all three poses. No clothing, hats, scenery, labels, words, watermarks, confetti or extra characters. Actual clean transparent background, never a drawn checkerboard. Deliver one wide sprite sheet.
```

## Consistency edit

The current atlas was edited with built-in ImageGen on 2026-09-26 to remove the completion pose's
reading glasses. The transparent three-pose layout is retained; the revised atlas measures 1944 × 809.

```text
Use case: precise-object-edit. Edit this transparent archive-otter sprite atlas. Change ONLY one thing: completely remove the violet reading glasses from the RIGHTMOST otter, reconstructing the eyes and surrounding fur to match the same bare-eyed otter in the left and middle poses. All three poses must now be without glasses. Preserve the original character, cut-paper collage style, expression, size, pose, whiskers, ticket, stamp, bookmark, brown/cream/violet palette, precise sprite placement and transparent background. Preserve the exact canvas aspect ratio and existing three-cell layout, positions, baselines and scale so this remains a drop-in sprite-sheet replacement. No cropping, no new objects, no new background, no text. Keep the left and middle otters unchanged.
```
