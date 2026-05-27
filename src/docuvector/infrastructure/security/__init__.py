"""Implementações concretas de serviços de segurança.

Bcrypt e JWT vivem aqui. O domínio enxerga apenas os Protocols
`PasswordHasher` e `TokenService`, podendo trocar a implementação
sem ripple effect.
"""
