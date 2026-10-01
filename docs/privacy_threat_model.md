# T028 privacy threat model

The protected asset is one participating controlled simulated client's clear model
update at the application-level central aggregation interface. The narrow objective
is to form the aggregate through Flower 1.39 SecAgg+ without presenting an
individual clear client model-update array to that instrumented interface.

The eight participants are controlled simulated research clients on one research
machine. Raw ECG windows, AAMI labels, and client minibatches are not application
messages sent to the server. This is an interface/data-locality observation, not a
claim of host or process isolation.

Non-goals are anonymity, differential privacy, resistance to every inference or
malicious-client attack, transport security, authentication, authorization,
OS/process isolation, production certification, real-hospital privacy, and
institution-scale security. Public keys, encrypted shares, masked vectors,
unmasking shares, aggregate state, client identifiers, and count metadata may be
visible as required by the protocol. No formal audit of Flower cryptography is
claimed.
