// Tiny C++ sample for the multilang fixture.

namespace geo {

struct Vec3 {
    double x;
    double y;
    double z;

    double dot(const Vec3& o) const {
        return x * o.x + y * o.y + z * o.z;
    }
};

class Sphere {
public:
    double radius() const {
        return 1.0;
    }
};

// Free function that calls Vec3::dot.
double length(const Vec3& v) {
    return v.dot(v);
}

}  // namespace geo
