# Tiny Julia sample for the multilang fixture.

module Geo

struct Circle
    r::Float64
end

function area(c::Circle)
    3.14159 * c.r^2
end

helper() = area(Circle(1.0))

end # module Geo
