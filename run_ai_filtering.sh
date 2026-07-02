#!/usr/bin/env bash

cat *.json >> input.json
#echo "------------" >> input.json
#cat ./international_news_el_mundo-export.json > input.json
#cat ./international_news_el_pais-export.json >> input.json

cat input.json | claude --dangerously-skip-permissions --model claude-haiku-4-5 -p "El archivo JSON incluye noticias internacionales de dos medios: 'elmundo.es' & 'elpais.com'. Quiero un resumen de las noticias dando mayor foco a las noticias con más entradas y luego un resumen de las que no se repiten. Si una noticia no sé repite, pero es parte de las de mayor foco, dejar en la primera sección de foco. Escribir el archivo resumen.html con los resultados e incluir en los resumenes referencias a las noticias originales. Cada sección debe ser colapsable." > resumen_reporte.txt

rm -y input.json

# Return only items worth reading, with a category, one-sentence summary, and tags.
# Respond as a JSON array — each item must have: id (integer), category (string), summary (string), tags (array of strings).
# Include ONLY items relevant to AI research or engineering. Omit everything else.
# Do not include any explanation or markdown — output ONLY the raw JSON array.
