#!/bin/bash
mkdir -p /logs/verifier

pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
rc=$?

if [ "$rc" -eq 0 ]; then
  echo -n 1 > /logs/verifier/reward.txt
else
  echo -n 0 > /logs/verifier/reward.txt
fi

exit 0
