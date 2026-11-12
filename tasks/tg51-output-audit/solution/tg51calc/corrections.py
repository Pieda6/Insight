"""Charge corrections: TG-51 Sec. VII (Eqs. 8-12) and addendum Eq. (3)."""
import numpy as np

T0 = 22.0
P0 = 101.33
TO_KPA = {'kPa': 1.0, 'hPa': 0.1, 'mmHg': 101.325 / 760.0, 'inHg': 3.386388640341}


def p_tp(temp, temp_unit, pressure, unit):
    """Eq. (10): water temperature near the chamber, barometer pressure (not corrected to sea level)."""
    t = (temp - 32.0) * 5.0 / 9.0 if temp_unit == 'F' else temp
    return (273.2 + t) / (273.2 + T0) * P0 / (pressure * TO_KPA[unit])


def p_pol(m_plus, m_minus, m_cal):
    """Eq. (9): signed readings, over the reading at the polarity of the chamber's calibration."""
    return abs((m_plus - m_minus) / (2.0 * m_cal))


def p_ion(m_high, m_low, v_high, v_low):
    """Eq. (12): two-voltage correction for pulsed beams."""
    r = v_high / v_low
    return (1.0 - r) / (m_high / m_low - r)


def corrected_reading(rows, chamber, electrometer, cross_calibrated=False):
    """Fully corrected reading per MU in nC (Eq. 8 / addendum Eq. 3 with Pleak = 1; Prp applied by the caller).

    Pelec is 1.00 for a cross-calibrated plane-parallel chamber (TG-51 Sec. VII.B)."""
    vh = float(chamber['operating_voltage_V'])
    cal = chamber['calibration_polarity']
    per_mu = lambda r: float(r['reading_nC']) / float(r['mu'])
    plus = next(r for r in rows if r['polarity'] == '+' and float(r['voltage_V']) == vh)
    minus = next(r for r in rows if r['polarity'] == '-' and float(r['voltage_V']) == vh)
    low = next(r for r in rows if r['polarity'] == cal and float(r['voltage_V']) < vh)
    main = plus if cal == '+' else minus
    m = per_mu(main)
    corr = p_tp(float(main['temperature']), main['temperature_unit'], float(main['pressure']), main['pressure_unit'])
    corr *= p_ion(m, per_mu(low), vh, float(low['voltage_V']))
    corr *= p_pol(per_mu(plus), per_mu(minus), m)
    corr *= 1.0 if cross_calibrated else electrometer['pelec'][main['electrometer_range']]
    return abs(m) * corr, main


def ndw_gy_per_c(chamber):
    return chamber['ndw'] * (1e7 if chamber['ndw_unit'] == 'cGy/nC' else 1.0)
