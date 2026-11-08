"""Domain: electronics at DC, worst case over every part's tolerance, temperature
coefficient and the stated ambient. Trusted physics in board (the component kind, its
lowering and grammar), network (the circuit quantities) and domain (modes, model premises,
builders, coverage); their source is the model premise's hash. generate, faults and gate
are tooling and change no verdict. docs/electronics_dc.md is the specification.
"""
from .domain import DOMAIN, MODEL_SPECS, NETWORK, NETWORK_LED, SOURCE

__all__ = ["DOMAIN", "MODEL_SPECS", "NETWORK", "NETWORK_LED", "SOURCE"]
