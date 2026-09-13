"""Génère une icône simple pour l'extension (128x128 PNG) : un bras robotique stylisé
avec un point d'arrêt (breakpoint) rouge sur une articulation — pas de génération
d'image IA disponible dans cet environnement, donc un design géométrique via PIL."""

from PIL import Image, ImageDraw

SIZE = 128
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Fond : carré arrondi bleu nuit
bg_color = (23, 32, 48, 255)
draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=24, fill=bg_color)

# Bras robotique stylisé : base -> coude -> poignet, en blanc cassé
arm_color = (230, 236, 245, 255)
joint_color = (120, 170, 230, 255)
stroke = 8

base = (30, 100)
elbow = (66, 50)
wrist = (98, 74)

draw.line([base, elbow], fill=arm_color, width=stroke)
draw.line([elbow, wrist], fill=arm_color, width=stroke)

# Base fixe (petit socle)
draw.rectangle([base[0] - 14, base[1] - 4, base[0] + 14, base[1] + 10], fill=arm_color)

# Articulations
for joint, r in [(base, 8), (elbow, 9), (wrist, 7)]:
    draw.ellipse(
        [joint[0] - r, joint[1] - r, joint[0] + r, joint[1] + r], fill=joint_color
    )

# Point d'arrêt (breakpoint) rouge sur le poignet
bp_r = 11
draw.ellipse(
    [wrist[0] - bp_r, wrist[1] - bp_r, wrist[0] + bp_r, wrist[1] + bp_r],
    fill=(220, 60, 60, 255),
    outline=(255, 255, 255, 255),
    width=2,
)

img.save("icon.png")
print("Écrit dans icon.png")
