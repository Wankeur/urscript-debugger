"""Instrumentation automatique d'un fichier .script : insère une fonction checkpoint_ask()
et un bloc de pause/reprise après CHAQUE ligne exécutable du bloc `def program():`, avec
envoi automatique de toutes les variables locales connues à ce point (détectées par
simple scan textuel des `local X =` précédant la ligne — pas un moteur de portée
complet, suffisant pour ce MVP).

Protocole (tout sur le même socket "dbg", qui reste ouvert le temps d'un checkpoint) :
1. Le script demande "dois-je m'arrêter ?" (checkpoint_ask) — réponse en un octet (0/1).
2. Si oui : le script exécute stopj() lui-même, confirme "ready" au serveur, PUIS entre
   dans une boucle de commandes tant qu'il n'a pas reçu l'ordre de reprendre :
   - commande 0 = reprendre (sort de la boucle)
   - commande 1 = affecter une variable locale connue à ce point (index + valeur ASCII),
     pour supporter l'édition de variables en direct depuis VS Code.
3. Si non : passage instantané, aucun impact sur un mouvement en cours.

Le mapping "nom de variable -> index" pour l'édition est déterminé par l'ORDRE des
variables locales connues à cet endroit précis du fichier (le même ordre que celui
envoyé dans `vars`) — chaque site de checkpoint génère son propre bloc d'affectation
car URScript ne permet pas d'assigner une variable dont le nom n'est connu qu'au
runtime (pas d'eval/accès dynamique aux variables locales).

Approche volontairement simple : insertion textuelle ligne à ligne, pas de parsing
sémantique complet. Suffisant car URScript délimite ses blocs avec des `end` explicites
(pas de dépendance à l'indentation pour la validité syntaxique). On suit juste la
profondeur de bloc pour savoir quand on est sorti du `def program():` et arrêter d'insérer.
"""

import argparse
import re

CHECKPOINT_ASK_FUNC = [
    "  def checkpoint_ask(label, is_breakpoint, vars):",
    '    socket_open("127.0.0.1", 29998, "dbg")',
    '    socket_send_string(label + "|" + to_str(is_breakpoint) + "|" + vars, "dbg")',
    '    local decision_list = socket_read_byte_list(1, "dbg", 0)',
    "    return decision_list[1]",
    "  end",
]

# Notification de fin de programme envoyée juste avant la sortie du bloc `def program():` —
# signal déterministe pour le serveur plutôt que de deviner via un sondage du dashboard
# (un programme rapide peut se terminer avant même le premier sondage).
PROGRAM_DONE_NOTICE = [
    '  socket_open("127.0.0.1", 29998, "dbg")',
    '  socket_send_string("PROGRAM_DONE", "dbg")',
    '  socket_close("dbg")',
]

LOCAL_DECL_RE = re.compile(r"^\s*local\s+(\w+)")


def _vars_expression(varnames: list[str]) -> str:
    """Construit l'expression URScript qui concatène "nom=valeur;..." pour toutes les variables connues."""
    if not varnames:
        return '""'
    parts = [f'"{name}=" + to_str({name})' for name in varnames]
    return ' + ";" + '.join(parts)


def _pause_block(indent: str, line_no: int, is_bp: int, vars_expr: str, known_locals: list[str]) -> list[str]:
    lines = [
        f'{indent}if checkpoint_ask("cp_line_{line_no}", {is_bp}, {vars_expr}) == 1:',
        f"{indent}  stopj(2.0)",
        f'{indent}  socket_send_string("ready", "dbg")',
        f'{indent}  local cmd_list = socket_read_byte_list(1, "dbg", 0)',
        f"{indent}  while cmd_list[1] == 1:",
        f'{indent}    local idx_list = socket_read_byte_list(1, "dbg", 0)',
        f'{indent}    local val_list = socket_read_ascii_float(1, "dbg", 0)',
    ]
    for i, name in enumerate(known_locals):
        lines += [
            f"{indent}    if idx_list[1] == {i}:",
            f"{indent}      {name} = val_list[1]",
            f"{indent}    end",
        ]
    lines += [
        f'{indent}    socket_send_string("ack", "dbg")',
        f'{indent}    cmd_list = socket_read_byte_list(1, "dbg", 0)',
        f"{indent}  end",
        f"{indent}end",
        f'{indent}socket_close("dbg")',
    ]
    return lines


def instrument(source: str, breakpoint_lines: set[int]) -> str:
    lines = source.splitlines()
    def_line_idx = next(i for i, l in enumerate(lines) if l.strip().startswith("def "))

    output = lines[: def_line_idx + 1] + CHECKPOINT_ASK_FUNC
    known_locals: list[str] = []
    depth = 1  # on est déjà à l'intérieur du `def program():`

    for i, line in enumerate(lines[def_line_idx + 1 :], start=def_line_idx + 1):
        stripped = line.strip()

        if depth <= 0:
            output.append(line)
            continue  # on est sorti du bloc def program(), ne plus rien instrumenter

        is_elif_else = stripped.startswith(("elif", "else"))
        is_block_header = stripped.endswith(":") and not is_elif_else
        is_end = stripped == "end"
        is_blank_or_comment = stripped == "" or stripped.startswith("#")

        if is_end and depth == 1:
            # On quitte le bloc def program() : notifier la fin avant le end qui le ferme.
            output += PROGRAM_DONE_NOTICE

        output.append(line)

        m = LOCAL_DECL_RE.match(line)
        if m:
            known_locals.append(m.group(1))

        line_no = i + 1
        should_checkpoint = not (is_block_header or is_end or is_elif_else or is_blank_or_comment)

        if should_checkpoint:
            indent = line[: len(line) - len(line.lstrip())]
            vars_expr = _vars_expression(known_locals)
            is_bp = 1 if line_no in breakpoint_lines else 0
            output += _pause_block(indent, line_no, is_bp, vars_expr, known_locals)

        if is_block_header:
            depth += 1
        elif is_end:
            depth -= 1

    return "\n".join(output) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("script_path")
    parser.add_argument("--break-at", type=int, action="append", default=[], dest="breakpoints")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()

    with open(args.script_path) as f:
        source = f.read()

    result = instrument(source, set(args.breakpoints))

    with open(args.output, "w") as f:
        f.write(result)

    print(f"Écrit dans {args.output}")
