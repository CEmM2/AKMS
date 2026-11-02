//! Tiny Rust sample for the multilang fixture.

pub struct Circle {
    pub r: f64,
}

impl Circle {
    pub fn new(r: f64) -> Circle {
        Circle { r }
    }

    pub fn area(&self) -> f64 {
        3.14159 * self.r * self.r
    }
}

pub trait Shape {
    fn name(&self) -> String;
}

/// Free function that calls Circle::new — resolves CONFIDENT to Circle::new.
pub fn helper() -> Circle {
    Circle::new(1.0)
}
