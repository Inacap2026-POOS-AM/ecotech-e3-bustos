from datetime import date


class RegistroTiempo:
    """Horas que un empleado le dedica a un proyecto en un día."""

    def __init__(self, empleado, proyecto, horas, fecha=None, descripcion=""):
        horas = float(horas)
        if horas <= 0 or horas > 24:
            raise ValueError("Las horas deben estar entre 0 y 24")
        self.empleado = empleado
        self.proyecto = proyecto
        self.horas = horas
        self.fecha = fecha or date.today()
        self.descripcion = descripcion
