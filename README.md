# IOF Foot-O Startlist Creation

Jupyter notebook for quick and easy startlist creation for IOF Foot-O events (WRE, Worldcup, etc.) following the [official rules](https://orienteering.sport/orienteering/competition-rules/) (Note: special rules of each year).  
Especially, rule 12.7 (no two runners from the same nation starting directly after another) is complied with. For the applying the special rules an eventSpecificFunction can be implemented following the exisiting implementation.  
The names entered to the competition should **exactly** be the same as already exisiting in the WRE system, if no match is found zero points for that runner are assumed.

The notebook includes a short proof of concept based on the [WC2 of 2023](https://eventor.orienteering.org/Events/Show/7247). 
Note that random draws can´t be reproduced without further information which also applies to two runners having the same amount of WRE points.

## Needs
- Firefox Browser installed (for automatically downloading the WRS as .csv files)
- Uses following Pyhton libraries: pandas, bs4, selenium, jupyterlab, ipykernel
Recommended: VS Code
