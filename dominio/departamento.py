class Departamento:
    def __init__(self, nombre, gerente=None):
        if not str(nombre).strip():
            raise ValueError("El departamento necesita nombre")
        self.nombre = str(nombre).strip()
        self.gerente = gerente
        self._empleados = []

    def agregar_empleado(self, empleado):
        if empleado not in self._empleados:
            self._empleados.append(empleado)
            empleado.departamento = self

    @property
    def empleados(self):
        return list(self._empleados)

    def __str__(self):
        return self.nombre
