-- Dans B0049 et B0051, Re/Rct de certains cycles d'impédance sont complexes (conjugués).
-- re_ohm / rct_ohm contiennent la partie réelle ; la partie imaginaire est conservée ici
-- (NULL quand elle est nulle) pour que le staging puisse décider quoi en faire.
ALTER TABLE raw.nasa_cycles ADD COLUMN IF NOT EXISTS re_imag_ohm  double precision;
ALTER TABLE raw.nasa_cycles ADD COLUMN IF NOT EXISTS rct_imag_ohm double precision;
