class Persona:
    """Clase base de la E1/E2: datos comunes de cualquier persona del sistema."""

    def __init__(self, rut, nombre):
        self.rut = rut
        self.nombre = nombre

    @property
    def rut(self):
        return self._rut

    @rut.setter
    def rut(self, valor):
        valor = str(valor).strip().upper().replace(".", "")
        if len(valor) < 3 or "-" not in valor:
            raise ValueError("RUT inválido, use el formato 12345678-9")
        self._rut = valor

    @property
    def nombre(self):
        return self._nombre

    @nombre.setter
    def nombre(self, valor):
        valor = str(valor).strip()
        if not valor:
            raise ValueError("El nombre no puede estar vacío")
        self._nombre = valor

    def __str__(self):
        return "%s (%s)" % (self.nombre, self.rut)
