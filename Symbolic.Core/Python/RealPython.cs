// =============================================================================
// Calcpad Suite Py — Puente al intérprete python real (subprocess)
// =============================================================================
//   Ejecuta un script en el `python` del sistema cuando el motor nativo C# no
//   alcanza (numpy, sympy, matplotlib, imports no nativos, etc.). Reusa el
//   patrón ya usado en Calcpad para bloques #python.
// =============================================================================
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace Calcpad.Core.Python
{
    public static class RealPython
    {
        /// <summary>Comando del intérprete (python / python3 / py). Configurable.</summary>
        public static string Interpreter { get; set; } = DefaultInterpreter();

        public static int TimeoutMs { get; set; } = 60000;

        private static string DefaultInterpreter()
            => OperatingSystem.IsWindows() ? "python" : "python3";

        public static (string Stdout, string Stderr, bool Ok) Execute(string code)
        {
            string tempFile = Path.Combine(Path.GetTempPath(), "calcpad_py_" + Guid.NewGuid().ToString("N") + ".py");
            try
            {
                File.WriteAllText(tempFile, code, new UTF8Encoding(false));
                var psi = new ProcessStartInfo
                {
                    FileName = Interpreter,
                    Arguments = $"-X utf8 \"{tempFile}\"",
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8,
                };
                psi.Environment["PYTHONIOENCODING"] = "utf-8";

                using var proc = Process.Start(psi);
                if (proc == null)
                    return ("", "No se pudo iniciar el intérprete de Python. ¿Está instalado y en el PATH?", false);

                var so = proc.StandardOutput.ReadToEnd();
                var se = proc.StandardError.ReadToEnd();
                if (!proc.WaitForExit(TimeoutMs))
                {
                    try { proc.Kill(true); } catch { }
                    return (so, "Timeout: el script Python excedió el tiempo límite.", false);
                }
                return (so, se, proc.ExitCode == 0);
            }
            catch (System.ComponentModel.Win32Exception)
            {
                return ("", $"No se encontró el intérprete '{Interpreter}'. Instalá Python o configurá RealPython.Interpreter.", false);
            }
            catch (Exception ex)
            {
                return ("", $"Error ejecutando Python: {ex.Message}", false);
            }
            finally
            {
                try { if (File.Exists(tempFile)) File.Delete(tempFile); } catch { }
            }
        }

        /// <summary>Ejecuta el script y entrega cada línea de stdout EN VIVO (a medida que
        /// Python la imprime), para mostrar el output línea por línea en el WebView2.
        /// Usa `-u` (unbuffered) + ReadLine en bucle. Devuelve (stderr, ok) al terminar.</summary>
        public static (string Stderr, bool Ok) ExecuteStreaming(string code, Action<string> onStdoutLine)
        {
            string tempFile = Path.Combine(Path.GetTempPath(), "calcpad_py_" + Guid.NewGuid().ToString("N") + ".py");
            try
            {
                File.WriteAllText(tempFile, code, new UTF8Encoding(false));
                var psi = new ProcessStartInfo
                {
                    FileName = Interpreter,
                    Arguments = $"-X utf8 -u \"{tempFile}\"",   // -u = stdout sin buffer → llega línea a línea
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8,
                };
                psi.Environment["PYTHONIOENCODING"] = "utf-8";
                psi.Environment["PYTHONUNBUFFERED"] = "1";

                using var proc = Process.Start(psi);
                if (proc == null)
                    return ("No se pudo iniciar el intérprete de Python. ¿Está instalado y en el PATH?", false);

                var stderr = new StringBuilder();
                proc.ErrorDataReceived += (_, e) => { if (e.Data != null) stderr.AppendLine(e.Data); };
                proc.BeginErrorReadLine();

                string line;
                while ((line = proc.StandardOutput.ReadLine()) != null)
                    onStdoutLine(line);                          // ← cada línea, EN VIVO

                if (!proc.WaitForExit(TimeoutMs))
                {
                    try { proc.Kill(true); } catch { }
                    return (stderr + "\nTimeout: el script Python excedió el tiempo límite.", false);
                }
                proc.WaitForExit();
                return (stderr.ToString(), proc.ExitCode == 0);
            }
            catch (System.ComponentModel.Win32Exception)
            {
                return ($"No se encontró el intérprete '{Interpreter}'. Instalá Python o configurá RealPython.Interpreter.", false);
            }
            catch (Exception ex)
            {
                return ($"Error ejecutando Python: {ex.Message}", false);
            }
            finally
            {
                try { if (File.Exists(tempFile)) File.Delete(tempFile); } catch { }
            }
        }

        /// <summary>Comprueba si hay un intérprete de Python disponible.</summary>
        public static bool IsAvailable()
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = Interpreter,
                    Arguments = "--version",
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
                using var proc = Process.Start(psi);
                if (proc == null) return false;
                proc.WaitForExit(5000);
                return true;
            }
            catch { return false; }
        }
    }
}
