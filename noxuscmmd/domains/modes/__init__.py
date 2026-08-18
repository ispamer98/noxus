"""Los modos de la casa: Fuera, En casa, Noche, Vacaciones.

Un modo NO es un motor nuevo. Es dos cosas, las dos apoyadas en lo que ya hay:

1. Una lista de reglas de automatización que se ejecutan al entrar en él. Se
   lanzan con el mismo `actions.dispatch` que usa el motor, así que un modo no
   sabe encender una luz — sabe pedirle al motor que ejecute la regla que sí
   sabe.

2. Una SEÑAL más para el motor. El modo activo entra en la foto del mundo igual
   que el armado o el estado de un sensor, así que cualquier regla puede
   dispararse «cuando la casa pasa a Noche» o pedir «solo si la casa está en
   Fuera», con el mismo editor de siempre.

De ahí que no haya editor de acciones propio: las acciones se montan donde se
han montado siempre, en Automatizaciones, y aquí solo se dice cuáles van con
cada modo.
"""
