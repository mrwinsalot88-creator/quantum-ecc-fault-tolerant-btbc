# Native balanced-trinary BTBC test note

Core BTBC state alphabet for this benchmark is the three-level basis `|-1>`, `|0>`, `|+1>`.

The benchmark deliberately does **not** use the binary `[[5,1,3]]` qubit code. It uses a 3-qutrit repetition encoding to isolate the first native-qutrit question: generalized-X cyclic shift errors plus noisy qutrit syndrome readout.

Controller semantics are frozen before execution:

- `0`: clear/reset
- `3`: first nonzero syndrome observation
- `6`: same syndrome observed again
- `9`: third matching observation triggers correction and reset

This is a clarity test for the native trinary architecture. It does not yet claim correction of generalized-Z phase errors or arbitrary qutrit noise.
