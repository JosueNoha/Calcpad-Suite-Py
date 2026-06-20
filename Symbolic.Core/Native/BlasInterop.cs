// =============================================================================
// Calcpad Lab — BLAS bindings (OpenBLAS DGEMM via P/Invoke)
// =============================================================================
//   OpenBLAS exporta `DGEMM` con Fortran calling convention:
//     - Todos los argumentos por referencia (ref/pointer)
//     - Layout column-major (transpuesto vs C row-major)
//     - Caracteres TRANSA/TRANSB pasados como pointers a byte
//
//   Truco column-major → row-major:
//     C = A*B (row-major) ≡ C^T = B^T * A^T (column-major)
//     Pasamos A_rowmajor como si fuera A^T_colmajor (K×M en col-major)
//     → DGEMM('N','N', n, m, k, 1, B_rowmajor, n, A_rowmajor, k, 0, C_rowmajor, n)
//
//   Threshold: BLAS solo conviene para matrices > 32×32 (sino la overhead
//   del DllImport call > compute de loop nativo).
// =============================================================================
using System;
using System.Runtime.InteropServices;

namespace Calcpad.Core
{
    public static class BlasInterop
    {
        private const string DllName = "libopenblas";
        private const byte NoTrans = (byte)'N';

        /// <summary>Threshold por debajo del cual usamos loop naive (overhead BLAS > compute).
        /// NOTA: libopenblas.dll necesita libxerbla.dll/libblas.dll que NO se incluyen
        /// en el bundle. BLAS solo funciona para llamadas que no triggeran xerbla
        /// (i.e., args válidos). Threshold 32 mantiene matrices pequeñas en naive
        /// (path seguro 100% managed).</summary>
        public const int BlasThreshold = 32;

        /// <summary>True si la DLL libopenblas.dll está disponible en runtime.</summary>
        public static readonly bool Available;

        static BlasInterop()
        {
            try
            {
                // Probe: tratar de llamar a una multiplicacion trivial 1×1
                var a = new[] { 2.0 };
                var b = new[] { 3.0 };
                var c = new[] { 0.0 };
                MatMul(1, 1, 1, a, b, c);
                Available = c[0] == 6.0;
            }
            catch
            {
                Available = false;
            }
        }

        [DllImport(DllName, EntryPoint = "DGEMM", CallingConvention = CallingConvention.Cdecl)]
        private static extern void DGEMM(
            ref byte transa,
            ref byte transb,
            ref int m,
            ref int n,
            ref int k,
            ref double alpha,
            [In] double[] A,
            ref int lda,
            [In] double[] B,
            ref int ldb,
            ref double beta,
            [In, Out] double[] C,
            ref int ldc);

        // DGEMV: y = alpha*A*x + beta*y (matrix-vector multiply)
        // Fortran prototype: dgemv_(trans, m, n, alpha, A, lda, x, incx, beta, y, incy)
        [DllImport(DllName, EntryPoint = "dgemv_", CallingConvention = CallingConvention.Cdecl)]
        private static extern void DGEMV(
            ref byte trans,
            ref int m,
            ref int n,
            ref double alpha,
            [In] double[] A,
            ref int lda,
            [In] double[] x,
            ref int incx,
            ref double beta,
            [In, Out] double[] y,
            ref int incy);

        // DAXPY: y = alpha*x + y (vector add scaled)
        [DllImport(DllName, EntryPoint = "daxpy_", CallingConvention = CallingConvention.Cdecl)]
        private static extern void DAXPY(
            ref int n,
            ref double alpha,
            [In] double[] x,
            ref int incx,
            [In, Out] double[] y,
            ref int incy);

        // DDOT: dot product = x · y
        [DllImport(DllName, EntryPoint = "ddot_", CallingConvention = CallingConvention.Cdecl)]
        private static extern double DDOT(
            ref int n,
            [In] double[] x,
            ref int incx,
            [In] double[] y,
            ref int incy);

        /// <summary>y[m] = A[m×n] * x[n] via DGEMV (BLAS L2 nativo).
        /// Para FEM: M_vec = D*Bm*Z_e (matrix-vector cascading). Mucho mas rapido
        /// que MatMul cuando n=1 (DGEMV es L2, DGEMM es L3 con overhead).</summary>
        public static void MatVec(int m, int n, double[] A, double[] x, double[] y)
        {
            if (!Available || m < BlasThreshold)
            {
                // Naive fallback: y = A*x row-major
                for (int i = 0; i < m; i++)
                {
                    double s = 0;
                    int rowA = i * n;
                    for (int j = 0; j < n; j++) s += A[rowA + j] * x[j];
                    y[i] = s;
                }
                return;
            }
            // Column-major trick: A_rowmajor visto como A^T_colmajor (n×m).
            // y = A_row * x  ≡  y = (A^T_col)^T * x  → trans='T', dim n×m, leading=n
            byte tT = (byte)'T';
            double alpha = 1.0, beta = 0.0;
            int mF = n, nF = m, lda = n, incx = 1, incy = 1;
            DGEMV(ref tT, ref mF, ref nF, ref alpha, A, ref lda, x, ref incx, ref beta, y, ref incy);
        }

        /// <summary>y[n] += alpha * x[n] via DAXPY. Para FEM: acumulacion de K_e.</summary>
        public static void Axpy(int n, double alpha, double[] x, double[] y)
        {
            if (!Available || n < BlasThreshold)
            {
                for (int i = 0; i < n; i++) y[i] += alpha * x[i];
                return;
            }
            int incx = 1, incy = 1;
            DAXPY(ref n, ref alpha, x, ref incx, y, ref incy);
        }

        /// <summary>dot product nativo via DDOT.</summary>
        public static double Dot(int n, double[] x, double[] y)
        {
            if (!Available || n < BlasThreshold)
            {
                double s = 0;
                for (int i = 0; i < n; i++) s += x[i] * y[i];
                return s;
            }
            int incx = 1, incy = 1;
            return DDOT(ref n, x, ref incx, y, ref incy);
        }

        /// <summary>
        /// C[m×n] = A[m×k] * B[k×n] (row-major) via OpenBLAS DGEMM column-major trick.
        /// Si las dimensiones son pequeñas (max < BlasThreshold) o si DLL no disponible,
        /// cae al loop naive.
        /// </summary>
        public static void MatMul(int m, int k, int n,
                                  double[] A, double[] B, double[] C)
        {
            // Always-correct fallback para tamaños chicos o sin BLAS
            int maxDim = m > n ? (m > k ? m : k) : (n > k ? n : k);
            if (!Available || maxDim < BlasThreshold)
            {
                MatMulNaive(m, k, n, A, B, C);
                return;
            }

            byte tN = NoTrans;
            double alpha = 1.0, beta = 0.0;
            int mF = n, nF = m, kF = k;      // Swap m↔n para el truco column-major
            int lda = n, ldb = k, ldc = n;   // leading dims
            // En column-major: pasamos B como "A" (mF×kF) y A como "B" (kF×nF).
            DGEMM(ref tN, ref tN, ref mF, ref nF, ref kF,
                  ref alpha, B, ref lda, A, ref ldb,
                  ref beta, C, ref ldc);
        }

        private static void MatMulNaive(int m, int k, int n, double[] A, double[] B, double[] C)
        {
            Array.Clear(C, 0, m * n);
            for (int i = 0; i < m; i++)
            {
                int rowA = i * k;
                int rowC = i * n;
                for (int p = 0; p < k; p++)
                {
                    double aip = A[rowA + p];
                    int rowB = p * n;
                    for (int j = 0; j < n; j++)
                        C[rowC + j] += aip * B[rowB + j];
                }
            }
        }
    }

    /// <summary>P/Invoke a LAPACK (libopenblas.dll, OpenMathLib v0.3.33+ que bundlea
    /// BLAS+LAPACK juntos). El liblapack.dll separado tenia dependencias rotas
    /// (libxerbla.dll, libblas.dll) que no estaban en el bundle.
    /// Fortran calling convention: todos los args por referencia, column-major.</summary>
    public static class LapackInterop
    {
        private const string DllName = "libopenblas";
        /// <summary>Threshold: DGESV solo conviene para n ≥ 64 (overhead transpose + dispatch).</summary>
        public const int LapackThreshold = 64;

        public static readonly bool Available;

        static LapackInterop()
        {
            try
            {
                // Probe: solve [1, 2; 3, 4] * x = [5; 11] → x = [1; 2]
                var A = new[] { 1.0, 3.0, 2.0, 4.0 };   // ya column-major
                var B = new[] { 5.0, 11.0 };
                var ipiv = new int[2];
                int n = 2, nrhs = 1, lda = 2, ldb = 2, info = 0;
                DGESV(ref n, ref nrhs, A, ref lda, ipiv, B, ref ldb, ref info);
                Available = info == 0 && Math.Abs(B[0] - 1.0) < 1e-9 && Math.Abs(B[1] - 2.0) < 1e-9;
            }
            catch
            {
                Available = false;
            }
        }

        [DllImport(DllName, EntryPoint = "dgesv_", CallingConvention = CallingConvention.Cdecl)]
        private static extern void DGESV(
            ref int n,
            ref int nrhs,
            [In, Out] double[] A,
            ref int lda,
            [In, Out] int[] ipiv,
            [In, Out] double[] B,
            ref int ldb,
            ref int info);

        /// <summary>DPBSV — Cholesky banded solve para matriz simétrica positive definite.
        /// Para K simétrica banded (FEM típico): O(n·bw²) en codigo Fortran optimizado.
        /// AB[ldab×n]: column-major banded storage (upper triangle):
        ///   AB(kd + 1 + i - j, j) = A(i, j) para max(1, j-kd) ≤ i ≤ j
        /// Lo cual en row-major C# se traduce a: para j en 0..n-1, copiar columna j superior.
        /// </summary>
        [DllImport(DllName, EntryPoint = "dpbsv_", CallingConvention = CallingConvention.Cdecl)]
        private static extern void DPBSV(
            ref byte uplo,
            ref int n,
            ref int kd,
            ref int nrhs,
            [In, Out] double[] AB,
            ref int ldab,
            [In, Out] double[] B,
            ref int ldb,
            ref int info);

        /// <summary>Resuelve A·x = b con A simétrica positive definite banded (bw=kd).
        /// A row-major n×n. Retorna x.</summary>
        public static double[] SolveSymBanded(int n, int kd, double[] A_row, double[] b)
        {
            if (!Available) throw new InvalidOperationException("LAPACK no disponible");
            // Banded upper storage column-major: AB[ldab × n], ldab = kd+1
            int ldab = kd + 1;
            var AB = new double[ldab * n];
            for (int j = 0; j < n; j++)
            {
                int iMin = System.Math.Max(0, j - kd);
                for (int i = iMin; i <= j; i++)
                    AB[j * ldab + (kd + i - j)] = A_row[i * n + j];
            }
            var x = new double[n];
            System.Array.Copy(b, x, n);
            byte uplo = (byte)'U';
            int N = n, KD = kd, nrhs = 1, ldb = n, info = 0;
            DPBSV(ref uplo, ref N, ref KD, ref nrhs, AB, ref ldab, x, ref ldb, ref info);
            if (info != 0)
                throw new InvalidOperationException($"DPBSV info={info} (not SPD or arg error)");
            return x;
        }

        /// <summary>
        /// Resuelve A·x = b para A cuadrada n×n y b vector n×1.
        /// A es row-major, b es 1D n-vector. Retorna x row-major.
        /// </summary>
        public static double[] Solve(int n, double[] A_row, double[] b)
        {
            if (!Available) throw new InvalidOperationException("LAPACK no disponible");
            // Transponer A row-major → column-major (A_row[i*n+j] → A_col[j*n+i])
            var A_col = new double[n * n];
            for (int i = 0; i < n; i++)
                for (int j = 0; j < n; j++)
                    A_col[j * n + i] = A_row[i * n + j];
            // b copy (DGESV lo sobreescribe con la solucion)
            var x = new double[n];
            Array.Copy(b, x, n);
            var ipiv = new int[n];
            int N = n, nrhs = 1, lda = n, ldb = n, info = 0;
            DGESV(ref N, ref nrhs, A_col, ref lda, ipiv, x, ref ldb, ref info);
            if (info != 0)
                throw new InvalidOperationException($"DGESV info={info} (singular or argument error)");
            return x;
        }
    }
}
