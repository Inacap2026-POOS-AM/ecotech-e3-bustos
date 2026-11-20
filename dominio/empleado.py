from .persona import Persona


class Empleado(Persona):
    def __init__(self, rut, nombre, sueldo_clp, departamento=None, id=None):
        super().__init__(rut, nombre)
        self.id = id
        self.sueldo_clp = sueldo_clp
        self.departamento = departamento

    @property
    def sueldo_clp(self):
        return self._sueldo_clp

    @sueldo_clp.setter
    def sueldo_clp(self, valor):
        valor = int(valor)
        if valor <= 0:
            raise ValueError("El sueldo debe ser mayor a cero")
        self._sueldo_clp = valor
