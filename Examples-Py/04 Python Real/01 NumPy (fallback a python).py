# %% NumPy — cae automáticamente al python real del sistema
# Cuando un script importa librerías no nativas (numpy, scipy, sympy,
# matplotlib, pandas...), Calcpad Suite Py lo ejecuta con el intérprete
# `python` instalado y muestra su salida. Requiere: pip install numpy
import numpy as np

# Matriz de rigidez de una barra axial (2x2)
E = 200000.0   # MPa
A = 2500.0     # mm2
L = 3000.0     # mm
k = E * A / L

K = k * np.array([[1, -1],
                  [-1, 1]])
print("Matriz de rigidez K [N/mm]:")
print(K)

# Vector de fuerzas y solución (con apoyo en nudo 0)
F = np.array([50000.0])          # N en nudo libre
Kred = K[1:, 1:]                 # condensar el GDL fijo
u = np.linalg.solve(Kred, F)
print(f"\nDesplazamiento nudo libre = {u[0]:.4f} mm")
