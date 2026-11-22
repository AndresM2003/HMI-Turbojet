from dataclasses import dataclass


@dataclass(frozen=True)
class OperatingLimits:
    """Umbrales usados por las listas de verificación de arranque y apagado.

    None = límite NO configurado. Un chequeo con límite sin configurar no se
    aprueba solo: queda en MANUAL y el operador debe confirmarlo mirando el valor.
    Los valores de seguridad los define el equipo del proyecto; este archivo no
    trae ninguno por defecto.
    """

    gas_ppm_max: float | None = None          # MQ6 1 y 2: máximo permitido antes del arranque
    maf_min_g_s: float | None = None          # flujo de aire mínimo que confirma aire establecido
    combustion_delta_c: float | None = None   # T3 - T2 mínimo que confirma combustión
    rpm_min: float | None = None              # RPM mínimas que confirman turbina girando
    cooldown_temp_c: float | None = None      # T3 y T4 por debajo de este valor = enfriado
    rpm_stopped_max: float | None = None      # RPM máximas que se consideran turbina detenida


LIMITS = OperatingLimits()
