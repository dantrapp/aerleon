use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[derive(Clone, Copy)]
struct Network {
    key: (u8, u128, u8),
    end: u128,
}

impl Network {
    fn new(version: u8, start: u128, prefix: u8) -> PyResult<Self> {
        let bits = match version {
            4 => 32,
            6 => 128,
            _ => return Err(PyValueError::new_err("expected IPv4 or IPv6")),
        };
        if prefix > bits || (version == 4 && start > u32::MAX.into()) {
            return Err(PyValueError::new_err("invalid network address or prefix"));
        }
        let host_bits = bits - prefix;
        let host_mask = if host_bits == 128 {
            u128::MAX
        } else {
            (1_u128 << host_bits) - 1
        };
        if start & host_mask != 0 {
            return Err(PyValueError::new_err("network address has host bits set"));
        }
        Ok(Self {
            key: (version, start, prefix),
            end: start | host_mask,
        })
    }
}

#[pyfunction]
fn address_book_indices(networks: Vec<(u8, u128, u8)>, existing: usize) -> PyResult<Vec<usize>> {
    if existing > networks.len() {
        return Err(PyValueError::new_err(
            "existing count exceeds network count",
        ));
    }
    let networks: Vec<Network> = networks
        .into_iter()
        .map(|(version, start, prefix)| Network::new(version, start, prefix))
        .collect::<PyResult<_>>()?;
    let mut incoming: Vec<usize> = (existing..networks.len()).collect();
    // Stable sorting and taking existing entries first on ties preserves metadata ownership.
    incoming.sort_by_key(|&index| networks[index].key);
    let mut selected = Vec::new();
    let (mut old, mut new) = (0, 0);
    let mut previous: Option<(u8, u128)> = None;
    while old < existing || new < incoming.len() {
        let index = if old < existing
            && (new == incoming.len() || networks[old].key <= networks[incoming[new]].key)
        {
            old += 1;
            old - 1
        } else {
            new += 1;
            incoming[new - 1]
        };
        let network = networks[index];
        if previous.is_some_and(|(version, end)| version == network.key.0 && network.end <= end) {
            continue;
        }
        previous = Some((network.key.0, network.end));
        selected.push(index);
    }
    Ok(selected)
}

#[pymodule]
fn _aerleon_probe(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(address_book_indices, module)?)?;
    Ok(())
}
