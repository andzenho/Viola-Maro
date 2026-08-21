#!/bin/sh
# Куски для вставки в блоки T123 Тильды — по одному файлу на страницу.
#
# Собирает все четыре версии лендинга плюс один комплект правовых страниц.
# Правовые страницы у всех версий совпадают дословно: различаются только
# неиспользуемые правила наведения в стилях, поэтому берём их из сборки
# оплаты и не плодим четыре одинаковых копии.
#
# Имена переменных латиницей намеренно: кириллица в них не работает,
# оболочка считает такую строку командой, а не присваиванием.
#
# Запуск:  sh tilda-собрать.sh
# Выход:   tilda/ — десять файлов и инструкция

set -e
TMP=".tilda-tmp"
OUT="tilda"

rm -rf "$TMP" "$OUT"
mkdir -p "$OUT"

for MODE in pay pre zayavka bron; do
  if [ "$MODE" = "pay" ]; then FLAG=""; else FLAG="--mode $MODE"; fi
  python3 build.py $FLAG --out "$TMP/src-$MODE" --tilda "$TMP/out-$MODE" >/dev/null
done

cp "$TMP/out-pay/index.html"     "$OUT/лендинг-оплата.html"
cp "$TMP/out-pre/index.html"     "$OUT/лендинг-предзапись.html"
cp "$TMP/out-zayavka/index.html" "$OUT/лендинг-заявка.html"
cp "$TMP/out-bron/index.html"    "$OUT/лендинг-бронь.html"

for DOC in offer offer-prilozhenie privacy consent consent-ads terms; do
  cp "$TMP/out-pay/$DOC.html" "$OUT/$DOC.html"
done

rm -rf "$TMP"

echo "Готово, $OUT/:"
ls -1sh "$OUT"
