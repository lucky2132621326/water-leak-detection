"""Machine-learning support for the acoustic channel.

`acoustic_features` is the single definition of how raw vibration telemetry
becomes a model feature vector. Both the training-export path and the runtime
detector import it. If those two ever computed features differently the model
would be scored on inputs it was never trained on, and the predictions would be
confident nonsense — the failure mode is silent, which is why there is exactly
one implementation rather than two that agree today.
"""
