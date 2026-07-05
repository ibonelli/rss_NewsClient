#!/usr/bin/env bash

cat transcript.txt | claude --dangerously-skip-permissions --model claude-haiku-4-5 -p "El texto provisto es la transcipción de un PODcast. Hacer un resumen de la entrevista y los puntos tratados." > resumen_reporte.txt
