"""Charge corrections, TG-51 Sec. VII (Eqs. 8-12)."""
import numpy as np

T0 = 22.0
P0 = 101.33
MMHG = 0.1333
TO_KPA = {'kPa': 1.0, 'hPa': 0.1, 'mmHg': MMHG}


def p_tp(temp_c, pressure, unit):
    """Eq. (10). Temperature of the water in deg C, pressure from the barometer."""
    p = pressure * TO_KPA[unit]
    return (273.2 + temp_c) / (273.2 + T0) * P0 / p


def p_pol(m_plus, m_minus):
    """Eq. (9). Readings carry their sign."""
    return np.abs((m_plus - m_minus) / (2.0 * np.abs(m_plus)))


def p_ion(m_high, m_low, v_high, v_low):
    """Two-voltage recombination correction."""
    r = v_high / v_low
    return (1. - r ** 2) / (m_high / m_low - r ** 2)


def corrected_reading(rows, chamber, electrometer):
    """Fully corrected reading per MU, Eq. (8)."""
    vh = chamber['operating_voltage_V']
    cal = chamber['calibration_polarity']
    plus = [r for r in rows if r['polarity'] == '+' and float(r['voltage_V']) == vh][0]
    minus = [r for r in rows if r['polarity'] == '-' and float(r['voltage_V']) == vh][0]
    low = [r for r in rows if r['polarity'] == cal and float(r['voltage_V']) != vh][0]
    main = plus if cal == '+' else minus
    per_mu = lambda r: np.float(r['reading_nC']) / int(r['mu'])
    m = per_mu(main)
    corr = p_tp(float(main['temperature']), float(main['pressure']), main['pressure_unit'])
    corr *= p_ion(m, per_mu(low), vh, float(low['voltage_V']))
    corr *= p_pol(per_mu(plus), per_mu(minus))
    corr *= electrometer['pelec']['high']
    return np.abs(m) * corr, main
